import ipaddress
import socket
import ssl
import time

import click
import requests
import routeros_api
from schema import Schema, Use
import toml

class Switch():
    def __init__(self, host, user, password):
        self.connection = routeros_api.RouterOsApiPool(
            host,
            username=user,
            password=password,
            port=8729,
            use_ssl=True,
            plaintext_login=True)
        self.get_state()

    def get_state(self):
        api = self.connection.get_api()
        ethernet = api.get_resource('/interface/ethernet')
        self.ethernet_details = ethernet.get()

    def get_comment(self, port):
        for interface in self.ethernet_details:
            if 'comment' in interface and interface['name'] == port:
                return interface['comment']
        return None

    def set_comment(self, port, comment):
        id = None
        for interface in self.ethernet_details:
            if interface['name'] == port:
                id = interface['id']
                break
        
        if not id:
            raise RuntimeError

        api = self.connection.get_api()
        ethernet = api.get_resource('/interface/ethernet')
        ethernet.set(id=id, comment=comment)

    def is_enabled(self, port):
        for interface in self.ethernet_details:
            if interface['name'] == port:
                if interface['disabled'] == 'false':
                    return True
        return False

    def disable_port(self, port):
        api = self.connection.get_api()
        ethernet = api.get_resource('/interface/ethernet')
        ethernet.call('disable', {'numbers': port})

    def enable_port(self, port):
        api = self.connection.get_api()
        ethernet = api.get_resource('/interface/ethernet')
        ethernet.call('enable', {'numbers': port})

def count_success(server, success):
    if success:
        server['fail_count'] = 0
        if 'ok_count' not in server:
            server['ok_count'] = 1
        else:
            server['ok_count'] += 1
    else:
        server['ok_count'] = 0
        if 'fail_count' not in server:
            server['fail_count'] = 1
        else:
            server['fail_count'] += 1

def monitor(switch, health_check_url, health_check_interval, servers):
    # Override getaddrinfo to return the value of current_ip
    current_ip = None
    prv_getaddrinfo = socket.getaddrinfo
    def new_getaddrinfo(*args):
        if current_ip:
            return prv_getaddrinfo(current_ip, *args[1:])
        else:
            return prv_getaddrinfo(*args)
    socket.getaddrinfo = new_getaddrinfo

    fail_comment = 'bonding-monitor health check fail'
    preparing_comment = 'bonding-monitor preparing to enable'

    while True:
        for server in servers:
            current_ip = str(server['server_ip'])
            try:
                r = requests.get(health_check_url)
            except:
                count_success(server, False)
                continue
            if r.ok:
                count_success(server, True)
            else:
                count_success(server, False)
        switch.get_state()
        for server in servers:
            # Goal: don't enable a port if any other monitor thinks it's down.
            comment = switch.get_comment(server['switch_port'])
            if server['fail_count'] >= 2 and switch.is_enabled(server['switch_port']):
                if not comment or comment != fail_comment:
                    switch.set_comment(server['switch_port'], fail_comment)
                if switch.is_enabled(server['switch_port']):
                    switch.disable_port(server['switch_port'])
            if server['ok_count'] >= 2 and not switch.is_enabled(server['switch_port']) and comment is not None:
                # If an interface is down with no comment, assume it has been manually disabled
                if comment != preparing_comment:
                    switch.set_comment(server['switch_port'], preparing_comment)
                elif server['ok_count'] >= 4:
                    # The server comment is still preparing_comment after four cycles, enable port and
                    switch.enable_port(server['switch_port'])
                    switch.set_comment(server['switch_port'], '')
        time.sleep(health_check_interval)
    pass

def parse_and_validate_config(config):
    config_schema = Schema({
        'health_check_url': str,
        'health_check_interval': int,
        'switch_host': str,
        'switch_user': str,
        'switch_password': str,
        'servers': [
            {
                'server_ip': Use(ipaddress.ip_address),
                'switch_port': str
            }
        ]})

    parsed_config = toml.load(config)
    return config_schema.validate(parsed_config)

def validate_ip(ctx, param, value):
    result = []
    try:
        for v in value:
            ip = ipaddress.ip_address(v)
            result.append(ip)
    except ValueError:
        raise click.BadParameter('IPv4 or IPv6 address required')
    return result

@click.command()
@click.option('-c', '--config', default="/etc/bonding-monitor/config.toml", type=click.File(), help="Configuration file, default: /etc/bonding-monitor/config.toml")
@click.option('--local-ip', help="Target with this IP address is on the local machine.", callback=validate_ip, multiple=True)
@click.option('--debug/--no-debug', default=False, help="Enable/disable debug output.")
def cli(config, local_ip, debug):
    """Monitor reachability of an URL at several target IPs. If a check
    fails, disable the corresponding port on a Mikrotik switch."""
    validated_config = parse_and_validate_config(config)
    
    # connectivity to a local ip tells us nothing
    non_local_servers = []
    for server in validated_config['servers']:
        if server['server_ip'] not in local_ip:
            non_local_servers.append(server)

    switch = Switch(validated_config['switch_host'], validated_config['switch_user'], validated_config['switch_password'])

    monitor(switch, validated_config['health_check_url'], validated_config['health_check_interval'], non_local_servers)

if __name__ == '__main__':
    cli(auto_envvar_prefix='BONDING_MONITOR') # pylint: disable=no-value-for-parameter,unexpected-keyword-arg