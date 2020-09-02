FROM richiefi/pipenv

COPY . /app

ENTRYPOINT ["python3", "bonding-monitor.py"]
