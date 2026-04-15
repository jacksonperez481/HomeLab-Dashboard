# Homelab Monitoring Dashboard

A lightweight monitoring dashboard built with FastAPI and Python to track system performance and network health.

## Features
- System metrics (CPU, memory, disk usage)
- Linux service monitoring (SSH, cron, Docker)
- Router monitoring (uptime and latency)
- Real-time updating web interface
- Color-coded health indicators
- Local subnet network scanner

## Tech Stack
- Python
- FastAPI
- psutil
- Linux systemctl
- HTML / JavaScript

## How to Run
1. Clone the repo
2. Create a virtual environment
3. Install dependencies:
   pip install -r requirements.txt
4. Run:
   uvicorn main:app --host 0.0.0.0 --port 8003

## Network Scanner

Scans the local subnet for active devices and checks for common open ports.

```bash
python3 network_scan.py
```

![Network Scanner](./assets/Screenshot%202026-04-14%20203239.png)

## Deployment (Linux Service)

The application is configured to run as a systemd service on a Linux server, allowing it to run continuously in the background and automatically start on system boot.

### Key Benefits:
- Persistent uptime (no manual startup required)
- Runs independently of terminal sessions
- Automatically restarts if the service stops

### Service Configuration:

```ini
[Unit]
Description=Homelab Dashboard API
After=network.target

[Service]
User=jacksonperez481
WorkingDirectory=/home/jacksonperez481/homelab-api
ExecStart=/home/jacksonperez481/homelab-api/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8003
Restart=always

[Install]
WantedBy=multi-user.target
```

## Screenshots

![Dashboard](./Screenshot%202026-04-05%20210558.png)

![Services](./Screenshot%202026-04-05%20210615.png)
