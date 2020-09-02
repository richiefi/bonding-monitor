# bonding-monitor

Turns out you can use interface bonding on Mikrotik switches to load balance server traffic at wire speeds. But the switch is not able to monitor the servers, at least not at L4 or higher, so we want a monitoring solution that can disable the component port of a failed server.

## Configuration

See `config.example.toml` for an example configuration.

The user account on the switch needs to belong to a group that has the `api`, `read` and `write` policies enabled. The switch needs to have a TLS certificate and the `api-ssl` service enabled.

## Running with Docker

The main branch of this repository is automatically built and uploaded to Docker Hub with the tag `richiefi/bonding-monitor:latest`. You can either use that are the baseline for your own Dockerfile or mount a configuration file into the container.

## Behavior

`bonding-monitor` checks reachability of each configured server in turn. If one or more local IPs were given on the command line, configured servers matching those IPs will be ignored (as monitoring the reachability of localhost is often less than useful).

If a server fails a health check twice in a row, its configured port on the switch will be disabled and the comment `bonding-monitor health check fail` set on the port.

If a server is healthy twice in a row, but the port on the switch is disabled due to a previous failure, `bonding-monitor` will change its comment to `bonding-monitor preparing to enable`. Finally, if a server is healthy for four consecutive checks and the port comment remains `bonding-monitor preparing to enable`, the port will be enabled and the comment removed.

You can run the monitor on multiple servers simultaneously; for example, on all of the servers of the monitored cluster.

## Known issues

There is a `--debug/--no-debug` flag but no debug output is currently available.
