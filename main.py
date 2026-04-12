from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import psutil
import socket
import time
import subprocess
import re
import os
import psycopg2
from contextlib import contextmanager
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
boot_time = psutil.boot_time()

router_ip = os.getenv("ROUTER_IP", "192.168.1.1")
router_last_up_time = None

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.1.214"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "homelab"),
    "user": os.getenv("DB_USER", "homelab_user"),
    "password": os.getenv("DB_PASSWORD", "homelab123"),
}

@contextmanager
def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    cpu_percent FLOAT,
                    memory_percent FLOAT,
                    disk_percent FLOAT,
                    router_online BOOLEAN,
                    latency_ms FLOAT
                )
            """)
        conn.commit()

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
        return {"online": online, "latency_ms": latency_ms}
    except Exception:
        return {"online": False, "latency_ms": None}

def collect_metrics():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    router = ping_host(router_ip)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO metrics (cpu_percent, memory_percent, disk_percent, router_online, latency_ms)
                    VALUES (%s, %s, %s, %s, %s)
                """, (cpu, memory.percent, disk.percent, router["online"], router["latency_ms"]))
            conn.commit()
    except Exception as e:
        print(f"DB error: {e}")

def check_service(service_name):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False

@app.on_event("startup")
def startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(collect_metrics, "interval", seconds=10)
    scheduler.start()

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})

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

@app.get("/services")
def services():
    service_status = {
        "ssh": check_service("ssh"),
        "cron": check_service("cron"),
        "docker": check_service("docker"),
    }
    overall_status = "healthy" if all(service_status.values()) else "warning"
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

@app.get("/metrics/history")
def metrics_history():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT timestamp, cpu_percent, memory_percent, disk_percent, router_online, latency_ms
                    FROM metrics
                    ORDER BY timestamp DESC
                    LIMIT 60
                """)
                rows = cur.fetchall()
        return [
            {
                "timestamp": row[0].isoformat(),
                "cpu_percent": row[1],
                "memory_percent": row[2],
                "disk_percent": row[3],
                "router_online": row[4],
                "latency_ms": row[5]
            }
            for row in rows
        ]
    except Exception as e:
        return {"error": str(e)}
