from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import psutil
import socket
import time
import subprocess
import re

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
boot_time = psutil.boot_time()

router_ip = "192.168.1.1"
router_last_up_time = None

def ping_host(ip_address):
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip_address],
            capture_output=True,
            text=True
        )

        output = result.stdout
        online = result.returncode == 0

        latency_ms = None
        if online:
            match = re.search(r'time=([\d.]+)\s*ms', output)
            if match:
                latency_ms = float(match.group(1))

        return {
            "online": online,
            "latency_ms": latency_ms
        }
    except Exception:
        return {
            "online": False,
            "latency_ms": None
        }

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request}
    )

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/system")
def system_health():
    uptime_seconds = time.time() - boot_time
    uptime_hours = round(uptime_seconds / 3600, 2)

    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    status = "healthy"
    if cpu > 90 or memory.percent > 90 or disk.percent > 90:
        status = "warning"

    return {
        "hostname": socket.gethostname(),
        "cpu_percent": cpu,
        "memory_percent": memory.percent,
        "disk_percent": disk.percent,
        "uptime_hours": uptime_hours,
        "status": status
    }

def check_service(service_name):
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


@app.get("/services")
def services():
    service_status = {
        "ssh": check_service("ssh"),
        "cron": check_service("cron"),
        "docker": check_service("docker"),
    }

    overall_status = "healthy"
    if not all(service_status.values()):
        overall_status = "warning"

    return {
        "hostname": socket.gethostname(),
        "services": service_status,
        "status": overall_status
    }
@app.get("/router")
def router_status():
    global router_last_up_time

    result = ping_host(router_ip)

    if result["online"]:
        if router_last_up_time is None:
            router_last_up_time = time.time()
        seen_up_for_seconds = round(time.time() - router_last_up_time, 1)
    else:
        router_last_up_time = None
        seen_up_for_seconds = None

    return {
        "ip": router_ip,
        "online": result["online"],
        "latency_ms": result["latency_ms"],
        "seen_up_for_seconds": seen_up_for_seconds
    }
