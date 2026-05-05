#!/usr/bin/env python3
"""
homelab-find.py — Find anything in your homelab instantly. No API key needed.

Usage:
    python3 homelab-find.py postgres
    python3 homelab-find.py "docker"
    python3 homelab-find.py --network
    python3 homelab-find.py --files myfile
"""

import json
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

API_BASE = "http://localhost:8003"
INVENTORY_FILE = Path(__file__).parent / "homelab-inventory.json"
HOME = Path("/home/jacksonperez481")

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RED    = "\033[91m"


def header(text):
    print(f"\n{BOLD}{CYAN}── {text} {RESET}")


def load_inventory() -> dict:
    if INVENTORY_FILE.exists():
        with open(INVENTORY_FILE) as f:
            return json.load(f).get("devices", {})
    return {}


def get_scan() -> dict:
    try:
        with urllib.request.urlopen(f"{API_BASE}/scan", timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def show_network(query: str = ""):
    header("Network Devices")
    inventory = load_inventory()
    scan = get_scan()
    hosts = scan.get("hosts", [])
    last_scan = scan.get("last_scan", "unknown")

    if not hosts:
        print(f"  {RED}Could not reach homelab API on port 8003{RESET}")
        return

    print(f"  {DIM}Last scan: {last_scan}{RESET}\n")

    for host in hosts:
        ip       = host["ip"]
        hostname = host.get("hostname", ip)
        ports    = host.get("ports", {})
        label    = inventory.get(ip, {})
        name     = label.get("name", "")
        desc     = label.get("description", "")

        open_ports = [f"{k}({v_name})" for k, v_open in ports.items()
                      if v_open for v_name in [_port_name(int(k))]]

        if query and query.lower() not in (ip + hostname + name + desc + " ".join(open_ports)).lower():
            continue

        display_name = f"{BOLD}{name}{RESET} — " if name else ""
        print(f"  {GREEN}{ip:<18}{RESET} {display_name}{DIM}{hostname}{RESET}")
        if desc:
            print(f"  {'':18} {DIM}{desc}{RESET}")
        if open_ports:
            print(f"  {'':18} ports: {CYAN}{', '.join(open_ports)}{RESET}")
        print()


def _port_name(port: int) -> str:
    names = {22: "SSH", 80: "HTTP", 443: "HTTPS", 3000: "Dev", 5432: "PostgreSQL", 8003: "Dashboard"}
    return names.get(port, str(port))


def search_files(query: str):
    header(f"Files matching '{query}'")
    result = subprocess.run(
        ["find", str(HOME), "-iname", f"*{query}*",
         "-not", "-path", "*/.git/*",
         "-not", "-path", "*/venv/*",
         "-not", "-path", "*/__pycache__/*",
         "-not", "-path", "*/.cache/*"],
        capture_output=True, text=True, timeout=15
    )
    matches = [l for l in result.stdout.strip().splitlines() if l]
    if matches:
        for m in matches[:25]:
            p = Path(m)
            icon = "📁" if p.is_dir() else "📄"
            print(f"  {icon} {m}")
    else:
        print(f"  {DIM}No files found matching '{query}'{RESET}")


def search_inside_files(query: str):
    header(f"Files containing '{query}'")
    result = subprocess.run(
        ["grep", "-rl", "--exclude-dir=.git", "--exclude-dir=venv",
         "--exclude-dir=__pycache__", "--exclude-dir=.cache",
         query, str(HOME)],
        capture_output=True, text=True, timeout=15
    )
    matches = [l for l in result.stdout.strip().splitlines() if l]
    if matches:
        for m in matches[:25]:
            print(f"  {CYAN}{m}{RESET}")
            try:
                lines = subprocess.run(
                    ["grep", "-n", query, m],
                    capture_output=True, text=True
                ).stdout.strip().splitlines()[:2]
                for line in lines:
                    print(f"    {DIM}{line}{RESET}")
            except Exception:
                pass
    else:
        print(f"  {DIM}No files contain '{query}'{RESET}")


def show_folder(path: str):
    header(f"Contents of {path}")
    p = Path(path).expanduser()
    if not p.exists():
        print(f"  {RED}{path} not found{RESET}")
        return
    for item in sorted(p.iterdir()):
        if item.name.startswith("."):
            continue
        try:
            size = item.stat().st_size
            size_str = f"{size:,} bytes" if size < 1024 else f"{size//1024} KB"
            icon = "📁" if item.is_dir() else "📄"
            print(f"  {icon} {item.name:<40} {DIM}{size_str}{RESET}")
        except Exception:
            pass


def smart_search(query: str):
    """Search everything — network + filenames + file contents."""
    print(f"\n{BOLD}Searching everything for: {CYAN}{query}{RESET}\n")
    show_network(query)
    search_files(query)
    search_inside_files(query)


def usage():
    print(f"""
{BOLD}homelab-find.py{RESET} — find anything in your homelab

  {CYAN}python3 homelab-find.py postgres{RESET}        search everything
  {CYAN}python3 homelab-find.py --network{RESET}       show all network devices
  {CYAN}python3 homelab-find.py --network ssh{RESET}   find devices with SSH
  {CYAN}python3 homelab-find.py --files nginx{RESET}   find files named nginx*
  {CYAN}python3 homelab-find.py --inside password{RESET} find files containing 'password'
  {CYAN}python3 homelab-find.py --ls ~/homelab-api{RESET} list a folder
""")


def main():
    args = sys.argv[1:]

    if not args:
        usage()
        return

    if args[0] == "--network":
        show_network(args[1] if len(args) > 1 else "")
    elif args[0] == "--files":
        if len(args) < 2:
            print("Usage: --files <name>")
        else:
            search_files(args[1])
    elif args[0] == "--inside":
        if len(args) < 2:
            print("Usage: --inside <text>")
        else:
            search_inside_files(args[1])
    elif args[0] == "--ls":
        if len(args) < 2:
            show_folder(str(HOME))
        else:
            show_folder(args[1])
    else:
        smart_search(" ".join(args))


if __name__ == "__main__":
    main()
