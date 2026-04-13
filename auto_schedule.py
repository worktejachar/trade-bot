# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
GX TradeIntel v6 — Auto Scheduler
====================================
Feature 4: Bot starts itself every morning. No manual intervention.

SETUP (run once):
  python auto_schedule.py --install

This adds crontab entries:
  8:55 AM  → Start the bot
  3:35 PM  → Force stop (safety)
  11:59 PM → Clean logs older than 30 days

After this, you NEVER need to type 'python start.py' again.
Bot runs Monday-Friday automatically.
"""
import os
import sys
import subprocess
import platform
from pathlib import Path


BOT_DIR = Path(__file__).parent.resolve()
PYTHON = sys.executable
START_SCRIPT = BOT_DIR / "start.py"
LOG_DIR = BOT_DIR / "logs"


def get_crontab_entries():
    """Generate crontab entries for auto-scheduling."""
    return [
        # Start bot at 8:55 AM, Monday to Friday
        f"55 8 * * 1-5 cd {BOT_DIR} && {PYTHON} {START_SCRIPT} >> {LOG_DIR}/cron.log 2>&1",
        # Safety: force kill at 3:35 PM in case bot didn't stop
        f"35 15 * * 1-5 pkill -f 'python.*start.py' >> {LOG_DIR}/cron.log 2>&1",
        # Clean old logs at midnight on Sunday
        f"0 0 * * 0 find {LOG_DIR} -name '*.log' -mtime +30 -delete",
    ]


def install_linux():
    """Install crontab entries on Linux/Mac."""
    entries = get_crontab_entries()

    # Read existing crontab
    try:
        existing = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        existing = ""

    # Remove old GX entries
    lines = [l for l in existing.strip().split("\n") if "GXTradeIntel" not in l and "start.py" not in l]

    # Add new entries with marker
    lines.append(f"\n# === GXTradeIntel v6 Auto-Schedule ===")
    for entry in entries:
        lines.append(entry)
    lines.append(f"# === End GXTradeIntel ===\n")

    # Write new crontab
    new_crontab = "\n".join(lines)
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
    proc.communicate(new_crontab.encode())

    print("✅ Crontab installed! Bot will auto-start at 8:55 AM Mon-Fri.")
    print()
    print("Schedule:")
    for e in entries:
        print(f"  {e.split(f'cd {BOT_DIR}')[0].strip()}")
    print()
    print("To verify: crontab -l")
    print("To remove: python auto_schedule.py --remove")


def remove_linux():
    """Remove GX crontab entries."""
    try:
        existing = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        print("No crontab found.")
        return

    lines = []
    skip = False
    for line in existing.split("\n"):
        if "GXTradeIntel" in line:
            skip = True
            continue
        if "End GXTradeIntel" in line:
            skip = False
            continue
        if not skip:
            lines.append(line)

    new_crontab = "\n".join(lines)
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
    proc.communicate(new_crontab.encode())
    print("✅ GX TradeIntel crontab entries removed.")


def show_windows_instructions():
    """Show Task Scheduler instructions for Windows."""
    print()
    print("══════════════════════════════════════════")
    print("  WINDOWS AUTO-SCHEDULE (Task Scheduler)")
    print("══════════════════════════════════════════")
    print()
    print("1. Open Task Scheduler (search in Start menu)")
    print("2. Click 'Create Basic Task'")
    print(f"3. Name: 'GX TradeIntel v6'")
    print(f"4. Trigger: Daily, 8:55 AM, Repeat Mon-Fri")
    print(f"5. Action: Start a Program")
    print(f"   Program: {PYTHON}")
    print(f"   Arguments: {START_SCRIPT}")
    print(f"   Start in: {BOT_DIR}")
    print()
    print("6. Create another task for safety stop:")
    print(f"   Time: 3:35 PM")
    print(f"   Action: taskkill /F /IM python.exe")
    print()
    print("That's it. Bot starts every morning automatically.")


def main():
    os.makedirs(LOG_DIR, exist_ok=True)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python auto_schedule.py --install   Install auto-start schedule")
        print("  python auto_schedule.py --remove    Remove auto-start schedule")
        print("  python auto_schedule.py --status    Show current schedule")
        return

    action = sys.argv[1].lower()
    system = platform.system().lower()

    if action == "--install":
        if system in ("linux", "darwin"):
            install_linux()
        else:
            show_windows_instructions()

    elif action == "--remove":
        if system in ("linux", "darwin"):
            remove_linux()
        else:
            print("On Windows, open Task Scheduler and delete the GX TradeIntel task.")

    elif action == "--status":
        if system in ("linux", "darwin"):
            try:
                crontab = subprocess.check_output(["crontab", "-l"]).decode()
                if "GXTradeIntel" in crontab:
                    print("✅ Auto-schedule is ACTIVE")
                    for line in crontab.split("\n"):
                        if "GXTradeIntel" in line or "start.py" in line:
                            print(f"  {line}")
                else:
                    print("❌ Auto-schedule not installed. Run: python auto_schedule.py --install")
            except Exception:
                print("❌ No crontab found.")
        else:
            print("On Windows, check Task Scheduler for GX TradeIntel task.")


if __name__ == "__main__":
    main()
