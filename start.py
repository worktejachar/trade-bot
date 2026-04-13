# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║       GX TRADEINTEL — QUICK START LAUNCHER       ║
║       Run this every morning before 9:15 AM      ║
╚══════════════════════════════════════════════════╝

Usage:
  python start.py          → Normal launch
  python start.py --setup  → First-time setup wizard
  python start.py --test   → Test all connections
  python start.py --paper  → Force paper trading mode
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime


CONFIG_FILE = "config.py"
CREDS_FILE = ".credentials.json"  # Local-only, never commit


def banner():
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║     🚀 GX TRADEINTEL v1.0 — Trading Bot         ║")
    print("║     Built by GarudawnX | Angel One SmartAPI      ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  📅 {datetime.now().strftime('%A, %d %B %Y | %H:%M:%S IST')}")
    print()


def check_dependencies():
    """Check and install required packages."""
    required = [
        "smartapi-python",
        "pyotp",
        "pandas",
        "numpy",
        "requests",
        "logzero",
    ]

    missing = []
    for pkg in required:
        pkg_import = pkg.replace("-", "_").replace("smartapi_python", "SmartApi")
        try:
            if pkg == "smartapi-python":
                __import__("SmartApi")
            else:
                __import__(pkg_import.split("_")[0] if "_" in pkg_import else pkg_import)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"  📦 Installing missing packages: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing, "-q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  ✅ All packages installed!")
    else:
        print("  ✅ All dependencies OK")


def setup_wizard():
    """Interactive first-time setup."""
    print("=" * 50)
    print("  🔧 FIRST-TIME SETUP WIZARD")
    print("=" * 50)
    print()

    creds = {}

    print("  📌 STEP 1: Angel One SmartAPI")
    print("  → Go to https://smartapi.angelbroking.com/")
    print("  → Create App → Get API Key")
    print()
    creds["ANGEL_API_KEY"] = input("  Enter API Key: ").strip()
    creds["ANGEL_CLIENT_ID"] = input("  Enter Client ID (e.g. A12345678): ").strip()
    creds["ANGEL_PASSWORD"] = input("  Enter PIN/MPIN: ").strip()

    print()
    print("  📌 STEP 2: TOTP Secret")
    print("  → Go to https://smartapi.angelbroking.com/enable-totp")
    print("  → Scan QR with Google Authenticator")
    print("  → Copy the TOTP secret (alphanumeric string)")
    print()
    creds["ANGEL_TOTP_SECRET"] = input("  Enter TOTP Secret: ").strip()

    print()
    print("  📌 STEP 3: Telegram Bot")
    print("  → Open Telegram → @BotFather → /newbot")
    print("  → Copy bot token")
    print("  → Then @userinfobot → Get your chat ID")
    print()
    creds["TELEGRAM_BOT_TOKEN"] = input("  Enter Bot Token: ").strip()
    creds["TELEGRAM_CHAT_ID"] = input("  Enter Chat ID: ").strip()

    print()
    print("  📌 STEP 4: Anthropic API (Optional — for AI news sentiment)")
    print("  → Get key from console.anthropic.com")
    print("  → Press Enter to skip")
    print()
    anthropic_key = input("  Enter Anthropic API Key (or Enter to skip): ").strip()
    if anthropic_key:
        creds["ANTHROPIC_API_KEY"] = anthropic_key

    # Save credentials to local file
    with open(CREDS_FILE, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)

    print()
    print("  ✅ Setup complete! Credentials saved.")
    print(f"  📁 Credentials stored in: {CREDS_FILE}")
    print("  ⚠️  NEVER share this file with anyone!")
    print("  💡 Config.py reads from this file automatically.")
    print()

    # Add to .gitignore
    gitignore = Path(".gitignore")
    if not gitignore.exists() or CREDS_FILE not in gitignore.read_text(encoding="utf-8", errors="ignore"):
        with open(".gitignore", "a", encoding="utf-8") as f:
            f.write(f"\n{CREDS_FILE}\n")

    return creds


def _update_config(creds):
    """Write credentials into config.py."""
    config_path = Path(CONFIG_FILE)
    if not config_path.exists():
        print(f"  ❌ {CONFIG_FILE} not found!")
        return

    content = config_path.read_text(encoding="utf-8")

    replacements = {
        "YOUR_API_KEY_HERE": creds.get("ANGEL_API_KEY", "YOUR_API_KEY_HERE"),
        "YOUR_CLIENT_ID": creds.get("ANGEL_CLIENT_ID", "YOUR_CLIENT_ID"),
        "YOUR_PIN": creds.get("ANGEL_PASSWORD", "YOUR_PIN"),
        "YOUR_TOTP_SECRET": creds.get("ANGEL_TOTP_SECRET", "YOUR_TOTP_SECRET"),
        "YOUR_BOT_TOKEN": creds.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN"),
        "YOUR_CHAT_ID": creds.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID"),
    }

    if "ANTHROPIC_API_KEY" in creds:
        replacements["YOUR_ANTHROPIC_KEY"] = creds["ANTHROPIC_API_KEY"]

    for old, new in replacements.items():
        content = content.replace(old, new)

    config_path.write_text(content, encoding="utf-8")
    print("  ✅ config.py updated with your credentials")


def load_saved_creds():
    """Load credentials from saved file."""
    if Path(CREDS_FILE).exists():
        with open(CREDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def test_connections():
    """Test all connections before going live."""
    print("  🧪 TESTING CONNECTIONS...")
    print()

    # Test 1: Angel One Login
    print("  [1/4] Angel One SmartAPI Login...", end=" ", flush=True)
    try:
        from broker import AngelOneBroker
        broker = AngelOneBroker()
        if broker.login():
            print("✅ Connected!")
            nifty = broker.get_nifty_ltp()
            if nifty:
                print(f"         Nifty LTP: ₹{nifty:,.2f}")
            broker.logout()
        else:
            print("❌ Login failed — check credentials")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Telegram
    print("  [2/4] Telegram Bot...", end=" ", flush=True)
    try:
        from alerts import TelegramAlerts
        alerts = TelegramAlerts()
        if alerts.send("🧪 <b>GX TradeIntel Test</b>\nConnection successful!"):
            print("✅ Message sent! Check Telegram.")
        else:
            if not alerts.enabled:
                print("⚠️  Not configured (will print to console)")
            else:
                print("❌ Failed to send")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 3: News Fetch
    print("  [3/4] News Feed...", end=" ", flush=True)
    try:
        from sentiment import NewsSentimentEngine
        engine = NewsSentimentEngine()
        news = engine.fetch_news(max_items=5)
        if news:
            print(f"✅ Fetched {len(news)} headlines")
        else:
            print("⚠️  No news fetched (RSS might be down)")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 4: Analysis Engine
    print("  [4/4] Analysis Engine...", end=" ", flush=True)
    try:
        from indicators import compute_all
        from regime import detect_regime
        import pandas as pd
        import numpy as np

        # Create dummy data to test
        dates = pd.date_range(end=datetime.now(), periods=50, freq="5min")
        dummy = pd.DataFrame({
            "timestamp": dates,
            "open": np.random.normal(24000, 50, 50),
            "high": np.random.normal(24050, 50, 50),
            "low": np.random.normal(23950, 50, 50),
            "close": np.random.normal(24000, 50, 50),
            "volume": np.random.randint(10000, 100000, 50),
        })
        ind_cfg = {"supertrend_period": 10, "supertrend_multiplier": 3, "ema_trend": 50,
                   "ema_fast": 9, "ema_slow": 21, "adx_period": 14, "rsi_period": 14,
                   "bb_period": 20, "bb_std": 2.0, "obv_lookback": 10}
        result = compute_all(dummy, ind_cfg)
        if "rsi" in result.columns:
            print("✅ All indicators working")
        else:
            print("❌ Indicators incomplete")
    except Exception as e:
        print(f"❌ Error: {e}")

    print()
    print("  " + "=" * 40)


def daily_launch(paper_mode=None):
    """Launch the trading bot."""
    now = datetime.now()
    hour = now.hour

    if hour < 8:
        print("  ⏰ Market hasn't opened yet. Bot will wait until 9:00 AM.")
        print("  💡 TIP: Run this between 8:45 - 9:15 AM for best results.")
        print()

    if hour >= 16:
        print("  🌙 Market is closed for today (closes 3:30 PM).")
        print("  💡 Run again tomorrow before 9:15 AM.")
        return

    if paper_mode is not None:
        import config
        config.PAPER_TRADE = paper_mode

    print(f"  📊 Mode: {'📝 PAPER TRADING (no real orders)' if True else '⚡ LIVE TRADING'}")
    print(f"  💰 Capital: ₹10,000")
    print(f"  🎯 Strategy: RSI + VWAP + EMA Confluence")
    print(f"  📱 Alerts: Telegram")
    print()
    print("  Starting bot... (Press Ctrl+C to stop)")
    print("  " + "=" * 40)
    print()

    from main import ConductorBot
    bot = ConductorBot()
    bot.run()


def main():
    banner()

    args = sys.argv[1:]

    # First-time check
    has_creds = Path(CREDS_FILE).exists()
    config_has_placeholders = False

    if Path(CONFIG_FILE).exists():
        content = Path(CONFIG_FILE).read_text(encoding="utf-8")
        config_has_placeholders = "YOUR_API_KEY_HERE" in content

    if "--setup" in args or (not has_creds and config_has_placeholders):
        print("  🔧 First-time setup detected!\n")
        check_dependencies()
        print()
        setup_wizard()
        print()

        run_test = input("  Run connection test? (y/n): ").strip().lower()
        if run_test == "y":
            test_connections()

        print()
        print("  ✅ All done! Run 'python start.py' tomorrow at 9 AM.")
        print("  📝 Bot starts in PAPER mode (no real trades).")
        print("  ⏰ After 2 weeks, change PAPER_TRADE to False in config.py")
        return

    if "--test" in args:
        check_dependencies()
        print()
        test_connections()
        return

    # Normal daily launch
    if config_has_placeholders and not has_creds:
        print("  ❌ Credentials not configured!")
        print("  Run: python start.py --setup")
        return

    # Load saved creds if config still has placeholders
    if config_has_placeholders and has_creds:
        creds = load_saved_creds()
        if creds:
            _update_config(creds)

    check_dependencies()
    print()

    paper = True  # Default paper
    if "--paper" in args:
        paper = True
    elif "--live" in args:
        paper = False
        print("  ⚡ LIVE MODE — Real orders will be placed!")
        confirm = input("  Type 'YES' to confirm: ").strip()
        if confirm != "YES":
            print("  Cancelled. Running in paper mode.")
            paper = True

    daily_launch(paper_mode=paper)


if __name__ == "__main__":
    main()
