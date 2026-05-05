#!/usr/bin/env python3
"""
linux_game.py — A terminal-based Linux learning game tailored to your homelab.
"""

import json
import os
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich import print as rprint

console = Console(width=100)

SAVE_FILE = os.path.join(os.path.dirname(__file__), "game_progress.json")

LEVELS = [
    {
        "title": "Level 1: Linux Basics",
        "description": "Core commands every Linux user needs to know. Type the command.",
        "questions": [
            {
                "q": "Type the command to list files in the current directory.",
                "accepted": ["ls"],
                "explanation": "`ls` lists directory contents. Add `-la` for detailed output including hidden files.",
            },
            {
                "q": "Type the command to print your current working directory.",
                "accepted": ["pwd"],
                "explanation": "`pwd` = Print Working Directory. Shows you exactly where you are in the filesystem.",
            },
            {
                "q": "Type the command to go to your home directory.",
                "accepted": ["cd ~", "cd"],
                "explanation": "`cd ~` or just `cd` takes you home. `~` is a shortcut for your home directory path.",
            },
            {
                "q": "Type the command to show the last 10 lines of a file called 'log.txt'.",
                "accepted": ["tail log.txt", "tail -10 log.txt", "tail -n 10 log.txt"],
                "explanation": "`tail` shows the end of a file. `tail -f log.txt` follows it live — great for watching logs.",
            },
            {
                "q": "Type the command to make a file called 'scan.py' executable.",
                "accepted": ["chmod +x scan.py"],
                "explanation": "`chmod +x` adds execute permission. Your network_scan.py uses this with the `#!/usr/bin/env python3` shebang.",
            },
        ],
    },
    {
        "title": "Level 2: File System & Permissions",
        "description": "Understanding how Linux organizes and protects files.",
        "questions": [
            {
                "q": "Type the full path of the directory that holds system configuration files.",
                "accepted": ["/etc"],
                "explanation": "`/etc` is where system-wide config files live — network config, cron settings, app configs.",
            },
            {
                "q": "Type the command to show disk usage of the current directory in human-readable format.",
                "accepted": ["du -sh", "du -sh ."],
                "explanation": "`du -sh` = Disk Usage, Summary, Human-readable. Great for finding what's eating your disk space.",
            },
            {
                "q": "Type the command to view the contents of a file called 'notes.txt'.",
                "accepted": ["cat notes.txt"],
                "explanation": "`cat` prints file contents to the terminal. For long files, use `less notes.txt` to scroll.",
            },
            {
                "q": "Type the command to create a new empty file called 'test.txt'.",
                "accepted": ["touch test.txt"],
                "explanation": "`touch` creates an empty file or updates the timestamp of an existing one.",
            },
            {
                "q": "Type the command to remove a file called 'old.txt'.",
                "accepted": ["rm old.txt"],
                "explanation": "`rm` removes files permanently — no trash bin on Linux. Use with care.",
            },
        ],
    },
    {
        "title": "Level 3: Networking",
        "description": "Networking from your homelab — subnet 192.168.1.0/24.",
        "questions": [
            {
                "q": "Type the command to send one ping to 192.168.1.1.",
                "accepted": ["ping -c 1 192.168.1.1", "ping 192.168.1.1"],
                "explanation": "Your network_scan.py uses `ping -c 1 -W 1` — one packet, wait one second. If it replies, the host is alive.",
            },
            {
                "q": "Type the default SSH port number.",
                "accepted": ["22"],
                "explanation": "Port 22 = SSH. Your scanner checks this port on every device. If open, you can connect remotely.",
            },
            {
                "q": "Type the subnet mask for a /24 network in dotted decimal notation.",
                "accepted": ["255.255.255.0"],
                "explanation": "/24 means 24 bits are the network portion. First three octets identify your network.",
            },
            {
                "q": "How many usable host IPs are in a /24 subnet? Type the number.",
                "accepted": ["254"],
                "explanation": "256 total addresses minus the network address (.0) and broadcast (.255) = 254 usable hosts.",
            },
            {
                "q": "Type the command to show your machine's IP address on Linux.",
                "accepted": ["ip a", "ip addr", "ip address", "ifconfig", "hostname -I"],
                "explanation": "`ip a` is the modern way. `ifconfig` is older but still common. Both show your network interfaces and IPs.",
            },
        ],
    },
    {
        "title": "Level 4: Cron & Automation",
        "description": "Scheduling tasks — like your 8 PM network scan.",
        "questions": [
            {
                "q": "Type the command to list your current cron jobs.",
                "accepted": ["crontab -l"],
                "explanation": "`crontab -l` lists your scheduled jobs. You ran this today to verify the network scanner.",
            },
            {
                "q": "Type the command to edit your cron jobs.",
                "accepted": ["crontab -e"],
                "explanation": "`crontab -e` opens your crontab in a text editor so you can add, edit, or remove jobs.",
            },
            {
                "q": "Your network scanner runs at 8 PM daily. Type the cron time expression for that (minute hour day month weekday).",
                "accepted": ["0 20 * * *"],
                "explanation": "Cron format: minute hour day month weekday. `0 20 * * *` = minute 0, hour 20 (8 PM), every day.",
            },
            {
                "q": "Type the shell command used to reload your .bashrc file in the current session.",
                "accepted": ["source ~/.bashrc", ". ~/.bashrc", "source .bashrc"],
                "explanation": "`source ~/.bashrc` reloads your shell config. We added this to your cron job so email credentials load correctly.",
            },
            {
                "q": "Type the file where your SCANNER_EMAIL credentials are stored.",
                "accepted": ["~/.bashrc", ".bashrc", "/home/jacksonperez481/.bashrc"],
                "explanation": "Your email credentials are exported as env vars in ~/.bashrc — never commit this file to GitHub.",
            },
        ],
    },
    {
        "title": "Level 5: Git & GitHub",
        "description": "Version control — what you used today to push your code.",
        "questions": [
            {
                "q": "Type the command to check the current state of your git repo (staged, unstaged, untracked).",
                "accepted": ["git status"],
                "explanation": "`git status` is your go-to. You used it today to see network_scan.py and known_hosts.json were modified.",
            },
            {
                "q": "Type the command to stage a file called 'network_scan.py' for commit.",
                "accepted": ["git add network_scan.py"],
                "explanation": "`git add` stages files. Think of it as putting things in a box before sealing it with a commit.",
            },
            {
                "q": "Type the command to push your local commits to the main branch on GitHub.",
                "accepted": ["git push origin main", "git push"],
                "explanation": "`push` sends your local commits up to GitHub. `origin` is the remote name, `main` is the branch.",
            },
            {
                "q": "Type the command to see your recent commit history.",
                "accepted": ["git log", "git log --oneline"],
                "explanation": "`git log` shows commit history with author, date, and message. `--oneline` makes it compact.",
            },
            {
                "q": "Type the GitHub CLI command you used today to log in to GitHub from the terminal.",
                "accepted": ["gh auth login"],
                "explanation": "`gh auth login` links your terminal to your GitHub account. We installed `gh` via webi since it wasn't on the server.",
            },
        ],
    },
    {
        "title": "Level 6: Homelab Stack",
        "description": "Your Proxmox, Terraform, and Docker setup.",
        "questions": [
            {
                "q": "Type the name of the hypervisor software running your VMs at home.",
                "accepted": ["proxmox", "proxmox ve"],
                "explanation": "Proxmox VE is a bare-metal hypervisor. It runs your VMs and LXC containers — the foundation of your homelab.",
            },
            {
                "q": "Type the tool used to provision VMs as code in your homelab.",
                "accepted": ["terraform"],
                "explanation": "Terraform lets you define your VMs in `.tf` files and provision them automatically — no clicking in a UI.",
            },
            {
                "q": "Type the file extension Terraform uses for its configuration files.",
                "accepted": [".tf", "tf"],
                "explanation": "`.tf` files are written in HCL (HashiCorp Configuration Language) — human-readable infrastructure-as-code.",
            },
            {
                "q": "Type the command to run a Python script called 'linux_game.py'.",
                "accepted": ["python3 linux_game.py"],
                "explanation": "`python3` runs Python 3 scripts. It's pre-installed on most Linux distros — same as your network scanner.",
            },
            {
                "q": "Type the IP address of your Ubuntu server (the one you SSH into).",
                "accepted": ["192.168.1.236"],
                "explanation": "192.168.1.236 — visible in your SSH login prompt today. It's on your homelab subnet 192.168.1.0/24.",
            },
        ],
    },
]


def normalize(s: str) -> str:
    return s.strip().lower()


def check_answer(user_input: str, accepted: list[str]) -> bool:
    user = normalize(user_input)
    return any(user == normalize(a) for a in accepted)


def load_progress() -> dict:
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE) as f:
            return json.load(f)
    return {"completed_levels": [], "scores": {}, "last_played": None}


def save_progress(progress: dict) -> None:
    progress["last_played"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SAVE_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def show_banner():
    console.print(Panel.fit(
        "[bold cyan]Linux Homelab Quest[/bold cyan]\n"
        "[dim]A game built from your actual environment — type your answers[/dim]",
        border_style="cyan"
    ))


def show_progress_table(progress: dict):
    table = Table(title="Your Progress", header_style="bold cyan", border_style="bright_black", show_lines=True)
    table.add_column("Level", min_width=35)
    table.add_column("Status", justify="center", min_width=10)
    table.add_column("Score", justify="center", min_width=10)

    for i, level in enumerate(LEVELS):
        level_key = str(i)
        if level_key in progress["completed_levels"]:
            status = "[green]Complete[/green]"
            score = progress["scores"].get(level_key, "?")
            score_str = f"[green]{score}/{len(level['questions'])}[/green]"
        elif i == 0 or str(i - 1) in progress["completed_levels"]:
            status = "[yellow]Available[/yellow]"
            score_str = "[dim]—[/dim]"
        else:
            status = "[dim]Locked[/dim]"
            score_str = "[dim]—[/dim]"
        table.add_row(level["title"], status, score_str)

    console.print(table)


def run_level(level_index: int, progress: dict) -> int:
    level = LEVELS[level_index]
    console.rule(f"[bold cyan]{level['title']}[/bold cyan]")
    rprint(f"[dim]{level['description']}[/dim]\n")

    score = 0
    total = len(level["questions"])

    for i, q in enumerate(level["questions"], 1):
        console.print(f"\n[bold white]Q{i}/{total}:[/bold white] {q['q']}\n")

        answer = Prompt.ask("[cyan]>[/cyan]")

        if check_answer(answer, q["accepted"]):
            rprint(f"\n[green]Correct![/green] {q['explanation']}")
            score += 1
        else:
            correct = q["accepted"][0]
            rprint(f"\n[red]Not quite.[/red] Expected: [bold]{correct}[/bold]\n{q['explanation']}")

        time.sleep(1)

    console.print()
    pct = int((score / total) * 100)
    if pct >= 80:
        rprint(f"[bold green]Level complete! {score}/{total} ({pct}%)[/bold green]")
        if str(level_index) not in progress["completed_levels"]:
            progress["completed_levels"].append(str(level_index))
    else:
        rprint(f"[bold yellow]Score: {score}/{total} ({pct}%). Need 80% to unlock the next level. Try again![/bold yellow]")

    progress["scores"][str(level_index)] = score
    return score


def main():
    show_banner()
    progress = load_progress()

    if progress["last_played"]:
        rprint(f"[dim]Last played: {progress['last_played']}[/dim]\n")

    while True:
        show_progress_table(progress)
        console.print()

        available = []
        for i in range(len(LEVELS)):
            if i == 0 or str(i - 1) in progress["completed_levels"]:
                available.append(str(i + 1))

        rprint(f"[dim]Available levels: {', '.join(available)}[/dim]")
        choice = Prompt.ask("\n[cyan]Pick a level (or 'q' to quit)[/cyan]")

        if choice.lower() == "q":
            rprint("[dim]See you next time.[/dim]")
            save_progress(progress)
            break

        if not choice.isdigit() or choice not in available:
            rprint("[red]That level isn't available yet.[/red]")
            continue

        level_index = int(choice) - 1
        run_level(level_index, progress)
        save_progress(progress)

        input("\nPress Enter to return to the menu...")
        console.clear()
        show_banner()


if __name__ == "__main__":
    main()
