#!/usr/bin/env python3
"""
homelab-agent.py — Ask plain-English questions about your homelab.

Usage:
    python3 homelab-agent.py
    python3 homelab-agent.py "where is my postgres server?"

Requires:
    pip install anthropic
    ANTHROPIC_API_KEY env var set
"""

import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import anthropic

API_BASE = "http://localhost:8003"
INVENTORY_FILE = Path(__file__).parent / "homelab-inventory.json"

client = anthropic.Anthropic()

# ─── Tools the agent can call ──────────────────────────────────────────────

def get_network_scan() -> dict:
    """Fetch the latest scan results from the homelab API."""
    try:
        with urllib.request.urlopen(f"{API_BASE}/scan", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e), "hint": "Is the homelab API running on port 8003?"}


def trigger_new_scan() -> dict:
    """Ask the API to run a fresh network scan."""
    try:
        req = urllib.request.Request(f"{API_BASE}/scan/start", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def get_inventory() -> dict:
    """Read the device inventory (friendly names and descriptions)."""
    if not INVENTORY_FILE.exists():
        return {"devices": {}, "notes": "Inventory file not found."}
    with open(INVENTORY_FILE) as f:
        return json.load(f)


def label_device(ip: str, name: str, description: str = "", tags: list[str] = []) -> dict:
    """Save a friendly name and description for a device IP."""
    inventory = get_inventory()
    inventory["devices"][ip] = {
        "name": name,
        "description": description,
        "tags": tags,
    }
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventory, f, indent=2)
    return {"saved": True, "ip": ip, "name": name}


def ping_device(ip: str) -> dict:
    """Ping a single IP right now to check if it's online."""
    result = subprocess.run(
        ["ping", "-c", "1", "-W", "1", ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"ip": ip, "online": result.returncode == 0}


def get_system_health() -> dict:
    """Get CPU, memory, disk, and uptime from the local machine running the API."""
    try:
        with urllib.request.urlopen(f"{API_BASE}/system", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def search_files(query: str, path: str = "/home/jacksonperez481", max_results: int = 20) -> dict:
    """Find files whose name contains the query string."""
    try:
        result = subprocess.run(
            ["find", path, "-iname", f"*{query}*", "-not", "-path", "*/.*",
             "-not", "-path", "*/venv/*", "-not", "-path", "*/__pycache__/*"],
            capture_output=True, text=True, timeout=10
        )
        matches = [l for l in result.stdout.strip().splitlines() if l][:max_results]
        return {"query": query, "path": path, "matches": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}


def list_directory(path: str) -> dict:
    """List the contents of a directory with file sizes."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"{path} does not exist"}
        items = []
        for item in sorted(p.iterdir()):
            if item.name.startswith("."):
                continue
            try:
                size = item.stat().st_size
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size_bytes": size,
                })
            except Exception:
                pass
        return {"path": str(p), "items": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


def find_in_files(query: str, path: str = "/home/jacksonperez481", extensions: list[str] = []) -> dict:
    """Search for text inside files. Optionally filter by extensions like ['py','txt']."""
    try:
        cmd = ["grep", "-rl", "--include=*", query, path]
        if extensions:
            cmd = ["grep", "-rl", query, path]
            for ext in extensions:
                cmd += ["--include", f"*.{ext}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        matches = [l for l in result.stdout.strip().splitlines() if l
                   and "/.git/" not in l and "/venv/" not in l and "/__pycache__/" not in l][:20]
        return {"query": query, "files_containing_match": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}


def get_folder_sizes(path: str = "/home/jacksonperez481") -> dict:
    """Show how much disk space each subfolder uses."""
    try:
        result = subprocess.run(
            ["du", "-sh", "--exclude=.git", "--exclude=venv", "--exclude=__pycache__",
             *[str(p) for p in Path(path).expanduser().iterdir() if not p.name.startswith(".")]],
            capture_output=True, text=True, timeout=15
        )
        lines = result.stdout.strip().splitlines()
        sizes = []
        for line in lines:
            parts = line.split("\t", 1)
            if len(parts) == 2:
                sizes.append({"size": parts[0], "path": parts[1]})
        sizes.sort(key=lambda x: x["path"])
        return {"path": path, "folders": sizes}
    except Exception as e:
        return {"error": str(e)}


# ─── Tool definitions for Claude ───────────────────────────────────────────

TOOLS = [
    {
        "name": "get_network_scan",
        "description": "Get the latest network scan results — all devices found on the subnet, their IPs, hostnames, and which ports are open. Use this to find where services are running.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "trigger_new_scan",
        "description": "Start a fresh network scan. Use this if the user wants up-to-date results or the last scan is old.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_inventory",
        "description": "Read the device inventory — friendly names, descriptions, and tags that have been saved for IPs. Combine this with scan results to give complete answers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "label_device",
        "description": "Save a friendly name and description for a device by IP address. Use this when the user tells you what a device is, or asks you to remember it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip":          {"type": "string", "description": "The IP address (e.g. 192.168.1.50)"},
                "name":        {"type": "string", "description": "Short friendly name (e.g. 'Game Server')"},
                "description": {"type": "string", "description": "What this device does"},
                "tags":        {"type": "array", "items": {"type": "string"}, "description": "Tags like ['server','game','docker']"},
            },
            "required": ["ip", "name"],
        },
    },
    {
        "name": "ping_device",
        "description": "Ping a single IP right now to check if it's currently online.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "IP address to ping"}
            },
            "required": ["ip"],
        },
    },
    {
        "name": "get_system_health",
        "description": "Get the current CPU, memory, disk usage and uptime of the machine running the homelab dashboard.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_files",
        "description": "Find files by name. Use this when the user asks where a file is or wants to find something by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Part of the filename to search for"},
                "path":        {"type": "string", "description": "Directory to search in (default: home folder)"},
                "max_results": {"type": "integer", "description": "Max number of results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_directory",
        "description": "List everything inside a folder. Use this when the user asks what's in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The folder path to list (e.g. /home/jacksonperez481/homelab-api)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "find_in_files",
        "description": "Search for text inside files. Use this when the user wants to find which file contains a certain word, config value, or code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string", "description": "Text to search for inside files"},
                "path":       {"type": "string", "description": "Directory to search in"},
                "extensions": {"type": "array", "items": {"type": "string"}, "description": "File extensions to limit search to, e.g. ['py', 'txt', 'yml']"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_folder_sizes",
        "description": "Show how much disk space each folder takes up. Use this when the user asks what's using space.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Parent folder to check sizes in"},
            },
            "required": [],
        },
    },
]

# ─── Tool dispatcher ────────────────────────────────────────────────────────

def run_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "get_network_scan":  lambda: get_network_scan(),
        "trigger_new_scan":  lambda: trigger_new_scan(),
        "get_inventory":     lambda: get_inventory(),
        "label_device":      lambda: label_device(**inputs),
        "ping_device":       lambda: ping_device(**inputs),
        "get_system_health": lambda: get_system_health(),
        "search_files":      lambda: search_files(**inputs),
        "list_directory":    lambda: list_directory(**inputs),
        "find_in_files":     lambda: find_in_files(**inputs),
        "get_folder_sizes":  lambda: get_folder_sizes(**inputs),
    }
    result = dispatch[name]()
    return json.dumps(result, indent=2)


# ─── Agent loop ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a homelab assistant. You help the user find and understand everything in their home network, servers, and files.

The user has:
- A 192.168.1.0/24 home network
- A Proxmox server managing VMs
- A homelab-api dashboard running on port 8003
- Docker containers (vaultwarden password manager, nginx reverse proxy, the dashboard itself)
- A PostgreSQL database at 192.168.1.214
- A router at 192.168.1.1
- Home directory: /home/jacksonperez481
- Projects: homelab-api, proxmox-terraform, linux_game.py

Finding network devices: use get_inventory first (friendly names), then get_network_scan (live data).
Finding files by name: use search_files.
Finding text inside files: use find_in_files.
Exploring a folder: use list_directory.
Checking disk usage: use get_folder_sizes.

When the user tells you what a device is, save it with label_device so you remember next time.

Be direct and specific — give exact paths, IPs, ports. Short answers are better than long ones."""


def ask(question: str, history: list[dict]) -> tuple[str, list[dict]]:
    history.append({"role": "user", "content": question})

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )

        # Collect assistant message
        assistant_content = response.content
        history.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    print(f"  [checking {block.name}...]")
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            history.append({"role": "user", "content": tool_results})
        else:
            # Extract final text response
            answer = next(
                (block.text for block in assistant_content if hasattr(block, "text")),
                ""
            )
            return answer, history


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is not set.")
        print("Get your key at https://console.anthropic.com and run:")
        print("  export ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    history = []

    # One-shot mode: python3 homelab-agent.py "your question"
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer, _ = ask(question, history)
        print(answer)
        return

    # Interactive mode
    print("Homelab Agent — ask anything about your network")
    print("Type 'exit' to quit\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "bye"):
            print("Bye!")
            break

        answer, history = ask(question, history)
        print(f"\nAgent: {answer}\n")


if __name__ == "__main__":
    main()
