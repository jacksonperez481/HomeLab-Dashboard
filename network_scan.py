#!/usr/bin/env python3
"""
network_scan.py — Local subnet scanner
Finds active hosts on a /24 subnet and checks for common open ports.
"""

import socket
import subprocess
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.table import Table
from rich import print as rprint

# ─────────────────────────────────────────────
# CONFIGURATION
# Change SUBNET to match your network.
# Add or remove ports from PORTS as needed.
# ─────────────────────────────────────────────
SUBNET = "192.168.1.0/24"
PORTS = [22, 80, 443, 3000, 5432, 8003]

# How many threads to use for scanning.
# Higher = faster, but more aggressive on the network.
PING_THREADS = 50
PORT_THREADS = 20

# Timeout in seconds when trying to connect to a port.
PORT_TIMEOUT = 0.5

# Well-known names for the ports we're scanning.
PORT_NAMES = {
    22:   "SSH",
    80:   "HTTP",
    443:  "HTTPS",
    3000: "Dev/Node",
    5432: "PostgreSQL",
    8003: "Alt HTTP",
}

console = Console(width=120)


# ─────────────────────────────────────────────
# STEP 1: PING SWEEP
# Send one ICMP ping to each IP. If it replies,
# the host is alive. We use the system `ping`
# command because sending raw ICMP packets
# requires root; this works as a normal user.
# ─────────────────────────────────────────────
def ping_host(ip: str) -> str | None:
    """
    Ping a single IP. Returns the IP string if alive, else None.
    -c 1  → send only 1 packet
    -W 1  → wait max 1 second for a reply
    stdout/stderr are suppressed so output stays clean.
    """
    result = subprocess.run(
        ["ping", "-c", "1", "-W", "1", ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return ip if result.returncode == 0 else None


def ping_sweep(subnet: str) -> list[str]:
    """
    Ping all IPs in the subnet in parallel using a thread pool.
    ThreadPoolExecutor lets us run many pings at once instead of
    waiting for each one to time out before moving to the next.
    Returns a sorted list of IPs that responded.
    """
    network = ipaddress.ip_network(subnet, strict=False)
    # Skip the network address (.0) and broadcast address (.255)
    hosts = [str(ip) for ip in network.hosts()]

    alive = []
    with ThreadPoolExecutor(max_workers=PING_THREADS) as executor:
        futures = {executor.submit(ping_host, ip): ip for ip in hosts}
        for future in as_completed(futures):
            result = future.result()
            if result:
                alive.append(result)

    # Sort numerically by the last octet so the table reads in order
    return sorted(alive, key=lambda ip: int(ip.split(".")[-1]))


# ─────────────────────────────────────────────
# STEP 2: PORT SCAN
# Try to open a TCP connection to each port.
# If the connection succeeds, the port is open.
# We close immediately — we just need to know
# if something is listening, not what it says.
# ─────────────────────────────────────────────
def check_port(ip: str, port: int) -> bool:
    """
    Attempt a TCP connect to ip:port.
    Returns True if the port accepts a connection (open), False otherwise.
    socket.create_connection is a higher-level wrapper around socket()
    that handles both IPv4 and IPv6 and raises on failure.
    """
    try:
        with socket.create_connection((ip, port), timeout=PORT_TIMEOUT):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def scan_ports(ip: str, ports: list[int]) -> dict[int, bool]:
    """
    Check all ports for a single host in parallel.
    Returns a dict like {22: True, 80: False, 443: True, ...}
    """
    results = {}
    with ThreadPoolExecutor(max_workers=PORT_THREADS) as executor:
        futures = {executor.submit(check_port, ip, port): port for port in ports}
        for future in as_completed(futures):
            port = futures[future]
            results[port] = future.result()
    return results


# ─────────────────────────────────────────────
# STEP 3: HOSTNAME LOOKUP
# Try to resolve each IP to a hostname using
# reverse DNS. If no hostname exists, we just
# show the IP. This is best-effort — it won't
# fail if the lookup times out.
# ─────────────────────────────────────────────
def resolve_hostname(ip: str) -> str:
    """
    Reverse-DNS lookup for a given IP.
    Returns the hostname, or the IP itself if lookup fails.
    """
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return ip


# ─────────────────────────────────────────────
# STEP 4: DISPLAY
# Build a rich Table and print it to the terminal.
# rich handles all the box-drawing, color, and
# alignment automatically.
# ─────────────────────────────────────────────
def build_table(scan_results: list[dict]) -> Table:
    """
    Takes a list of result dicts and returns a formatted rich Table.
    Each dict has keys: ip, hostname, ports (a dict of port→bool).
    """
    table = Table(
        title=f"Network Scan — {SUBNET}",
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        show_lines=True,
    )

    # Fixed columns
    table.add_column("IP Address", style="bold white", min_width=15)
    table.add_column("Hostname", style="dim white", min_width=20)

    # One column per port
    for port in PORTS:
        label = f"{port}\n[dim]{PORT_NAMES.get(port, '')}[/dim]"
        table.add_column(label, justify="center", min_width=10)

    for host in scan_results:
        ip       = host["ip"]
        hostname = host["hostname"]
        ports    = host["ports"]

        # Build a cell for each port: green check or red dash
        port_cells = []
        for port in PORTS:
            if ports.get(port):
                port_cells.append("[green]OPEN[/green]")
            else:
                port_cells.append("[red dim]—[/red dim]")

        table.add_row(ip, hostname, *port_cells)

    return table


# ─────────────────────────────────────────────
# MAIN
# Orchestrates the sweep → scan → display flow.
# ─────────────────────────────────────────────
def main():
    console.rule("[bold cyan]Network Scanner[/bold cyan]")
    rprint(f"[dim]Subnet:[/dim] [bold]{SUBNET}[/bold]   "
           f"[dim]Ports:[/dim] [bold]{', '.join(map(str, PORTS))}[/bold]\n")

    # Phase 1: find live hosts
    console.print("[yellow]Phase 1:[/yellow] Pinging all hosts...", end=" ")
    alive = ping_sweep(SUBNET)
    console.print(f"[green]{len(alive)} host(s) found[/green]")

    if not alive:
        rprint("[red]No hosts responded to ping. Check your subnet or firewall rules.[/red]")
        return

    # Phase 2: scan ports on each live host
    console.print("[yellow]Phase 2:[/yellow] Scanning ports...", end=" ")
    scan_results = []
    for ip in alive:
        hostname = resolve_hostname(ip)
        ports    = scan_ports(ip, PORTS)
        scan_results.append({"ip": ip, "hostname": hostname, "ports": ports})
    console.print("[green]Done[/green]\n")

    # Phase 3: display results
    table = build_table(scan_results)
    console.print(table)

    # Summary line
    total_open = sum(
        1 for host in scan_results for open_ in host["ports"].values() if open_
    )
    rprint(f"\n[dim]Scanned {len(alive)} host(s) · {total_open} open port(s) found[/dim]")


if __name__ == "__main__":
    main()
