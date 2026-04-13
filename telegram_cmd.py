# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Telegram Command Interface
=================================================
Gap 5: Mobile/Dashboard → Telegram becomes your command center.
Commands:
  /status  — Current bot status, active engine, positions
  /signal  — Force a scan and get current signal
  /pnl     — Today's P&L summary
  /feeds   — Live data feeds (FII/DII, VIX, OI, crude)
  /regime  — Current market regime
  /stop    — Pause the bot
  /start   — Resume the bot
  /health  — System health check
"""
import logging
import threading
import time as t_
from datetime import datetime

import requests
import config

logger = logging.getLogger("GXTradeIntel.TelegramCmd")


class TelegramCommander:
    """Listens for commands on Telegram and executes them."""

    def __init__(self, bot_ref=None):
        self.bot = bot_ref  # Reference to ConductorBot
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = self.token != "YOUR_BOT_TOKEN"
        self.last_update_id = 0
        self._running = False
        self._thread = None

    def start_listening(self):
        """Start background thread to poll for commands."""
        if not self.enabled:
            logger.info("Telegram commands disabled (no token)")
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("📱 Telegram command listener started")

    def stop_listening(self):
        self._running = False

    def _poll_loop(self):
        """Poll for new messages every 3 seconds."""
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except Exception as e:
                logger.debug(f"Telegram poll error: {e}")
            t_.sleep(3)

    def _get_updates(self):
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            resp = requests.get(url, params={
                "offset": self.last_update_id + 1,
                "timeout": 2,
            }, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
        except Exception:
            pass
        return []

    def _handle_update(self, update):
        self.last_update_id = update.get("update_id", self.last_update_id)
        message = update.get("message", {})
        text = message.get("text", "").strip().lower()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Security: only respond to configured chat
        if chat_id != str(self.chat_id):
            return

        if text == "/status":
            self._cmd_status()
        elif text == "/pnl":
            self._cmd_pnl()
        elif text == "/feeds":
            self._cmd_feeds()
        elif text == "/regime":
            self._cmd_regime()
        elif text == "/signal":
            self._cmd_signal()
        elif text == "/stop":
            self._cmd_stop()
        elif text == "/resume":
            self._cmd_resume()
        elif text == "/health":
            self._cmd_health()
        elif text == "/help":
            self._cmd_help()

    def _send(self, text):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }, timeout=10)
        except Exception as e:
            logger.warning(f"Telegram send error: {e}")

    # ── Commands ──

    def _cmd_status(self):
        if not self.bot:
            self._send("⚠️ Bot reference not set")
            return

        engine = self.bot.active_engine or "NONE"
        positions = [p for p in self.bot.risk.positions if p.is_open]
        pos_text = "No open positions"
        if positions:
            p = positions[0]
            pnl_est = "N/A"
            pos_text = f"{p.symbol} | {p.direction} | Entry: ₹{p.entry_price:.2f} | {p.holding_minutes}min"

        conductor = self.bot.conductor_decision or {}

        self._send(
            f"📊 <b>BOT STATUS</b>\n\n"
            f"<b>Running:</b> {'Yes' if self.bot.running else 'No'}\n"
            f"<b>Mode:</b> {'PAPER' if config.PAPER_TRADE else 'LIVE'}\n"
            f"<b>Active Engine:</b> {engine}\n"
            f"<b>Conductor Conf:</b> {conductor.get('confidence', 'N/A')}%\n"
            f"<b>Regime:</b> {self.bot.regime_data.get('regime', 'N/A')}\n"
            f"<b>Trades Today:</b> {self.bot.risk.daily_trades}\n"
            f"<b>Position:</b> {pos_text}\n"
            f"<b>Daily P&L:</b> ₹{self.bot.risk.daily_pnl:+,.2f}\n"
            f"⏰ {datetime.now():%H:%M:%S IST}"
        )

    def _cmd_pnl(self):
        if not self.bot:
            return
        stats = self.bot.risk.daily_stats()
        self._send(
            f"💰 <b>TODAY'S P&L</b>\n\n"
            f"Trades: {stats['trades']}\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Win Rate: {stats['win_rate']}%\n"
            f"Net P&L: ₹{stats['pnl']:+,.2f}\n"
            f"Capital: ₹{stats['capital_after']:,.2f}"
        )

    def _cmd_feeds(self):
        if not self.bot or not hasattr(self.bot, 'live_data'):
            self._send("⚠️ Live data hub not available")
            return
        summary = self.bot.live_data.get_summary_text()
        self._send(summary)

    def _cmd_regime(self):
        if not self.bot:
            return
        r = self.bot.regime_data
        self._send(
            f"📈 <b>MARKET REGIME</b>\n\n"
            f"<b>Regime:</b> {r.get('regime', 'N/A')}\n"
            f"<b>Confidence:</b> {r.get('confidence', 0)}%\n"
            f"<b>Direction:</b> {r.get('direction', 'N/A')}\n"
            f"<b>ADX:</b> {r.get('adx', 'N/A')}\n"
            f"<b>ATR Ratio:</b> {r.get('atr_ratio', 'N/A')}\n"
            f"<b>BB:</b> {'Expanding' if r.get('bb_expanding') else 'Contracting'}\n"
            f"<b>Scores:</b> T={r.get('scores', {}).get('TRENDING', 0)} "
            f"R={r.get('scores', {}).get('RANGING', 0)} "
            f"V={r.get('scores', {}).get('VOLATILE', 0)}"
        )

    def _cmd_signal(self):
        self._send("🔍 Force scanning... Results will appear shortly.")
        # Trigger a scan cycle in the main bot
        if self.bot and self.bot.running:
            try:
                self.bot.scan_cycle()
            except Exception as e:
                self._send(f"⚠️ Scan error: {e}")

    def _cmd_stop(self):
        if self.bot:
            self.bot.running = False
            self._send("🛑 Bot PAUSED. Send /resume to restart.")

    def _cmd_resume(self):
        if self.bot:
            self.bot.running = True
            self._send("▶️ Bot RESUMED.")

    def _cmd_health(self):
        checks = []
        checks.append(f"{'✅' if self.bot and self.bot.running else '❌'} Bot running")
        checks.append(f"{'✅' if self.bot and self.bot.broker.connected else '❌'} Angel One connected")
        checks.append(f"{'✅' if self.enabled else '❌'} Telegram active")
        checks.append(f"{'✅' if config.ANTHROPIC_API_KEY != 'YOUR_ANTHROPIC_KEY' else '⚠️'} Claude API configured")

        self._send(
            f"🏥 <b>SYSTEM HEALTH</b>\n\n" + "\n".join(checks) +
            f"\n\n⏰ {datetime.now():%H:%M:%S IST}"
        )

    def _cmd_help(self):
        self._send(
            "📋 <b>COMMANDS</b>\n\n"
            "/status — Bot status & active engine\n"
            "/pnl — Today's P&L\n"
            "/feeds — Live data (FII, VIX, OI, crude)\n"
            "/regime — Market regime analysis\n"
            "/signal — Force a market scan\n"
            "/stop — Pause the bot\n"
            "/resume — Resume the bot\n"
            "/health — System health check\n"
            "/help — This message"
        )
