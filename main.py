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
import ipaddress
import threading
import smtplib
import json
from email.mime.text import MIMEText
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    checks = {
        "ssh":    lambda: any("sshd" in open(f"/proc/{p}/comm").read() for p in os.listdir("/proc") if p.isdigit()),
        "cron":   lambda: any("cron" in open(f"/proc/{p}/comm").read() for p in os.listdir("/proc") if p.isdigit()),
        "docker": lambda: any("dockerd" in open(f"/proc/{p}/comm").read() for p in os.listdir("/proc") if p.isdigit()),
    }
    try:
        return checks[service_name]()
    except Exception:
        return False

def send_daily_report():
    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print("Email not configured — skipping daily report")
        return

    try:
        inv = json.loads(INVENTORY_FILE.read_text()) if INVENTORY_FILE.exists() else {}
    except Exception:
        inv = {}
    inv_devices = inv.get("devices", {})

    hosts = scan_state.get("hosts", [])
    last_scan = scan_state.get("last_scan", "No scan yet")
    new_devices = scan_state.get("new_devices", [])

    hosts_with_time = sorted(
        [(h, device_first_seen[h["ip"]]) for h in hosts if h["ip"] in device_first_seen],
        key=lambda x: x[1],
    )

    lines = [
        "Homelab Daily Network Report",
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Last Scan : {last_scan}",
        "",
        "=== NETWORK OVERVIEW ===",
        f"Devices Online: {len(hosts)}",
        "",
    ]

    if new_devices:
        lines.append("⚠️  SUSPICIOUS / NEW DEVICES DETECTED:")
        for d in new_devices:
            name = inv_devices.get(d["ip"], {}).get("name", "Unknown")
            lines.append(f"  - {d['ip']} ({d['hostname']}) — {name}")
        lines.append("")
    else:
        lines.append("✅ No new or suspicious devices detected.")
        lines.append("")

    lines.append("=== DEVICE TIME ON NETWORK ===")
    if hosts_with_time:
        longest_host, longest_ts = hosts_with_time[0]
        longest_name = inv_devices.get(longest_host["ip"], {}).get("name", "Unknown")
        lines.append(f"Longest connected: {longest_host['ip']} ({longest_name}) — {format_duration(time.time() - longest_ts)}")
        lines.append("")
        for h, first_ts in hosts_with_time:
            name = inv_devices.get(h["ip"], {}).get("name", "Unknown")
            lines.append(f"  {h['ip']:<16} {name:<22} {format_duration(time.time() - first_ts)}")
    else:
        lines.append("No device time data available yet.")

    lines += [
        "",
        "=== ALL DEVICES ONLINE ===",
    ]
    for h in hosts:
        name = inv_devices.get(h["ip"], {}).get("name", "Unknown")
        open_ports = [PORT_NAMES.get(p, str(p)) for p, is_open in h["ports"].items() if is_open]
        lines.append(f"  {h['ip']:<16} {name:<22} Ports: {', '.join(open_ports) or 'none'}")

    body = "\n".join(lines)
    subject = f"Homelab Daily Report — {datetime.now().strftime('%Y-%m-%d')}"

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"Daily report sent to {EMAIL_TO}")
    except Exception as e:
        print(f"Failed to send daily report: {e}")


@app.on_event("startup")
def startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(collect_metrics, "interval", seconds=10)
    scheduler.add_job(lambda: threading.Thread(target=run_scan, daemon=True).start(), "interval", minutes=15)
    scheduler.add_job(send_daily_report, "cron", hour=8, minute=0)
    scheduler.start()
    threading.Thread(target=run_scan, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/system")
def system_health():
    uptime_seconds = time.time() - boot_time
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
        "uptime_seconds": round(uptime_seconds),
        "uptime_formatted": format_duration(uptime_seconds),
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
        seen_up_for_seconds = round(time.time() - router_last_up_time)
    else:
        router_last_up_time = None
        seen_up_for_seconds = None
    return {
        "ip": router_ip,
        "online": result["online"],
        "latency_ms": result["latency_ms"],
        "seen_up_for_seconds": seen_up_for_seconds,
        "seen_up_for_formatted": format_duration(seen_up_for_seconds),
    }

SUBNET = os.getenv("SUBNET", "192.168.1.0/24")
SCAN_PORTS = [22, 80, 443, 3000, 5432, 8003]
PORT_NAMES = {22: "SSH", 80: "HTTP", 443: "HTTPS", 3000: "Dev", 5432: "PostgreSQL", 8003: "Dashboard"}

EMAIL_FROM = os.getenv("SCANNER_EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("SCANNER_EMAIL_PASSWORD", "")
EMAIL_TO = os.getenv("SCANNER_EMAIL_RECIPIENT", EMAIL_FROM)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
INVENTORY_FILE = Path("/home/jacksonperez481/homelab-inventory.json")

scan_state = {"scanning": False, "last_scan": None, "hosts": [], "new_devices": []}
known_ips = set()
device_first_seen: dict[str, float] = {}

def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    s = int(seconds)
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    minutes, secs = divmod(s, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _ping(ip):
    result = subprocess.run(["ping", "-c", "1", "-W", "1", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ip if result.returncode == 0 else None

def _check_port(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=0.5):
            return True
    except Exception:
        return False

def _resolve(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ip

def run_scan():
    global known_ips, device_first_seen
    scan_state["scanning"] = True
    now = time.time()
    hosts = [str(ip) for ip in ipaddress.ip_network(SUBNET, strict=False).hosts()]
    alive = []
    with ThreadPoolExecutor(max_workers=50) as ex:
        for result in as_completed({ex.submit(_ping, ip): ip for ip in hosts}):
            if result.result():
                alive.append(result.result())
    alive = sorted(alive, key=lambda ip: int(ip.split(".")[-1]))
    current_ips = set(alive)
    new_ips = current_ips - known_ips if known_ips else set()
    for ip in alive:
        if ip not in device_first_seen:
            device_first_seen[ip] = now
    results = []
    for ip in alive:
        ports = {}
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = {ex.submit(_check_port, ip, port): port for port in SCAN_PORTS}
            for f in as_completed(futures):
                ports[futures[f]] = f.result()
        seen_for = round(time.time() - device_first_seen[ip])
        results.append({
            "ip": ip,
            "hostname": _resolve(ip),
            "ports": ports,
            "is_new": ip in new_ips,
            "seen_for_seconds": seen_for,
        })
    known_ips = current_ips
    scan_state["scanning"] = False
    scan_state["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scan_state["hosts"] = results
    scan_state["new_devices"] = [r for r in results if r["is_new"]]

@app.get("/scan")
def get_scan():
    return scan_state

@app.post("/scan/start")
def start_scan():
    if scan_state["scanning"]:
        return {"message": "Scan already in progress"}
    threading.Thread(target=run_scan, daemon=True).start()
    return {"message": "Scan started"}

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
