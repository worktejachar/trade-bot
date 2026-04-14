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
        elif text == "/why":
            self._cmd_why()
        elif text == "/settings":
            self._cmd_settings()
        elif text.startswith("/ask"):
            self._cmd_ask(text)
        elif text.startswith("/explain"):
            self._cmd_explain(text)
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

        # Engine name in plain English
        engine = self.bot.active_engine or "NONE"
        engine_names = {
            "MOMENTUM": "Momentum (riding trends)",
            "MEAN_REVERSION": "Mean Reversion (buy low, sell high)",
            "SCALPER": "Scalper (quick in-and-out trades)",
            "NONE": "None — waiting for the right setup",
        }
        engine_desc = engine_names.get(engine, engine)

        positions = [p for p in self.bot.risk.positions if p.is_open]
        if positions:
            p = positions[0]
            pos_text = f"Yes — {p.symbol}, entered at ₹{p.entry_price:.2f}, held for {p.holding_minutes} min"
        else:
            pos_text = "No open trades right now."

        mode = "PAPER (practice mode, no real money)" if config.PAPER_TRADE else "LIVE (real money)"

        self._send(
            f"📊 <b>Bot Status</b>\n\n"
            f"Bot is {'ON and watching the market' if self.bot.running else 'PAUSED (not trading)'}.\n"
            f"Mode: {mode}\n"
            f"Currently using: {engine_desc}\n"
            f"Trades today: {self.bot.risk.daily_trades}\n"
            f"Open position: {pos_text}\n"
            f"Today's P&L: ₹{self.bot.risk.daily_pnl:+,.2f}\n"
            f"Capital: ₹{config.TOTAL_CAPITAL:,}\n"
            f"⏰ {datetime.now():%H:%M:%S IST}"
        )

    def _cmd_pnl(self):
        if not self.bot:
            return
        stats = self.bot.risk.daily_stats()
        trades = stats['trades']

        if trades == 0:
            summary = "No trades today."
        elif stats['pnl'] > 0:
            summary = f"Won {stats['wins']}, lost {stats['losses']} ({stats['win_rate']}% win rate)."
        else:
            summary = f"Won {stats['wins']}, lost {stats['losses']} ({stats['win_rate']}% win rate)."

        pnl = stats['pnl']
        if pnl > 0:
            pnl_text = f"+₹{pnl:,.2f} (profit)"
        elif pnl < 0:
            pnl_text = f"-₹{abs(pnl):,.2f} (loss)"
        else:
            pnl_text = "₹0 (no change)"

        self._send(
            f"💰 <b>Today's Profit/Loss</b>\n\n"
            f"Today's result: {pnl_text}\n"
            f"Trades taken: {trades}\n"
            f"{summary}\n"
            f"Total capital: ₹{stats['capital_after']:,.2f}"
        )

    def _cmd_feeds(self):
        if not self.bot or not hasattr(self.bot, 'live_data'):
            self._send("⚠️ Live data not available right now.")
            return
        ld = self.bot.live_data
        fii = ld.fii_dii.get("fii_net", 0)
        dii = ld.fii_dii.get("dii_net", 0)
        vix = ld.vix
        crude = ld.crude

        fii_dir = "Buying" if fii > 0 else "Selling"
        dii_dir = "Buying" if dii > 0 else "Selling"

        if vix < 15:
            vix_desc = "low — calm market"
        elif vix < 22:
            vix_desc = "moderate — normal day expected"
        elif vix < 30:
            vix_desc = "high — expect bigger swings"
        else:
            vix_desc = "very high — market is fearful!"

        self._send(
            f"📡 <b>Live Market Data</b>\n\n"
            f"Big investors (FII): {fii_dir} ₹{abs(fii):,.0f} Cr today\n"
            f"Indian funds (DII): {dii_dir} ₹{abs(dii):,.0f} Cr today\n"
            f"Fear level (VIX): {vix:.1f} ({vix_desc})\n"
            f"Oil price: ${crude:.0f} per barrel"
        )

    def _cmd_regime(self):
        if not self.bot:
            return
        r = self.bot.regime_data
        regime = r.get('regime', 'N/A')

        # Plain English regime descriptions
        regime_info = {
            "TRENDING": (
                "TRENDING (moving in one direction)",
                "Price is moving steadily up or down.",
                "Momentum — ride the trend."
            ),
            "RANGING": (
                "SIDEWAYS (ranging)",
                "Price is bouncing between levels, not trending.",
                "Mean Reversion — buy low, sell high."
            ),
            "VOLATILE": (
                "VOLATILE (big swings)",
                "Price is making large, unpredictable moves.",
                "Scalper — quick in-and-out trades."
            ),
        }
        desc = regime_info.get(regime, (regime, "Unable to determine.", "Waiting."))

        self._send(
            f"📈 <b>Market Type Today</b>\n\n"
            f"Market type: <b>{desc[0]}</b>\n"
            f"What it means: {desc[1]}\n"
            f"Best strategy for this: {desc[2]}\n"
            f"Confidence: {r.get('confidence', 0)}%"
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
        checks.append(f"{'✅' if self.bot and self.bot.running else '❌'} Bot is running")
        checks.append(f"{'✅' if self.bot and self.bot.broker.connected else '❌'} Connected to Angel One")
        checks.append(f"{'✅' if self.enabled else '❌'} Telegram is working")
        checks.append(f"{'✅' if config.ANTHROPIC_API_KEY != 'YOUR_ANTHROPIC_KEY' else '⚠️'} AI brain (Claude) connected")

        self._send(
            f"🏥 <b>System Health Check</b>\n\n" + "\n".join(checks) +
            f"\n\nEverything {'looks good!' if all('✅' in c for c in checks) else 'needs attention.'}"
            f"\n⏰ {datetime.now():%H:%M:%S IST}"
        )

    def _cmd_why(self):
        """Explain the last decision the bot made."""
        if not self.bot:
            return

        regime = self.bot.regime_data.get('regime', 'N/A')
        engine = self.bot.active_engine or "NONE"
        conductor = self.bot.conductor_decision or {}
        confidence = conductor.get('confidence', 0)
        positions = [p for p in self.bot.risk.positions if p.is_open]

        if positions:
            p = positions[0]
            reason = (
                f"I entered a trade on {p.symbol} at ₹{p.entry_price:.2f}.\n"
                f"The market was {regime.lower()} and the {engine} strategy gave "
                f"a {confidence}% confidence signal. The setup matched my rules."
            )
        elif self.bot.risk.daily_trades > 0:
            reason = (
                f"I took {self.bot.risk.daily_trades} trade(s) today and closed them.\n"
                f"The market was {regime.lower()}. I used the {engine} strategy."
            )
        else:
            # Explain why no trades
            reasons = []
            if regime == "N/A":
                reasons.append("I couldn't determine the market type clearly.")
            if confidence < config.CONDUCTOR.get("min_conductor_confidence", 60):
                reasons.append(f"Confidence was only {confidence}% (I need at least {config.CONDUCTOR.get('min_conductor_confidence', 60)}%).")
            if not reasons:
                reasons.append("No setup matched all my rules today.")

            reason = (
                f"No trades today. Here's why:\n"
                + "\n".join(f"- {r}" for r in reasons)
                + f"\n\nMarket type: {regime}. "
                f"Taking a trade without a strong signal would likely lose money. "
                f"I'll wait for better conditions."
            )

        self._send(f"🤔 <b>Why did I do that?</b>\n\n{reason}")

    def _cmd_settings(self):
        """Show current settings in plain English."""
        mode = "PAPER (practice — no real money)" if config.PAPER_TRADE else "LIVE (real money!)"
        self._send(
            f"⚙️ <b>Your Settings</b>\n\n"
            f"Capital: ₹{config.TOTAL_CAPITAL:,}\n"
            f"Max risk per trade: ₹{config.MAX_RISK_PER_TRADE:,.0f} ({config.MAX_RISK_PER_TRADE_PCT}%)\n"
            f"Max trades per day: {config.MAX_TRADES_PER_DAY}\n"
            f"Mode: {mode}\n"
            f"Stop trading if down: ₹{config.MAX_DAILY_LOSS:,.0f} in a day\n"
            f"Weekly loss limit: ₹{config.MAX_WEEKLY_LOSS:,.0f}\n"
            f"Execution: {config.EXECUTION_MODE}\n"
            f"Instruments: {', '.join(config.ACTIVE_INSTRUMENTS)}"
        )

    def _cmd_ask(self, text):
        """Answer a user question based on current bot state."""
        question = text.replace("/ask", "").strip()
        if not question:
            self._send(
                "Ask me anything! Examples:\n"
                "/ask why didn't you trade today?\n"
                "/ask what's the market doing?\n"
                "/ask how much have I made this week?"
            )
            return

        # Build a contextual answer from current state
        if not self.bot:
            self._send("⚠️ Bot is not running, can't answer right now.")
            return

        regime = self.bot.regime_data.get('regime', 'N/A')
        engine = self.bot.active_engine or "NONE"
        stats = self.bot.risk.daily_stats()
        pnl = stats.get('pnl', 0)
        trades = stats.get('trades', 0)

        # Simple keyword matching for common questions
        q = question.lower()
        if any(w in q for w in ["why no trade", "why didn't", "why not trading", "why waiting"]):
            self._cmd_why()
        elif any(w in q for w in ["market", "nifty", "what's happening"]):
            self._send(
                f"The market is currently <b>{regime}</b>.\n"
                f"I'm using the <b>{engine}</b> strategy.\n"
                f"Trades today: {trades}, P&L: ₹{pnl:+,.2f}"
            )
        elif any(w in q for w in ["risk", "how much can i lose", "safe"]):
            self._send(
                f"Your max risk per trade is ₹{config.MAX_RISK_PER_TRADE:,.0f} "
                f"({config.MAX_RISK_PER_TRADE_PCT}% of capital).\n"
                f"I'll stop trading if you lose ₹{config.MAX_DAILY_LOSS:,.0f} in a day.\n"
                f"Your capital is protected by multiple safety limits."
            )
        elif any(w in q for w in ["capital", "money", "balance"]):
            self._send(
                f"Your capital: ₹{config.TOTAL_CAPITAL:,}\n"
                f"Today's P&L: ₹{pnl:+,.2f}\n"
                f"Active capital (70%): ₹{config.ACTIVE_CAPITAL:,.0f}\n"
                f"Reserve (30%): ₹{config.TOTAL_CAPITAL - config.ACTIVE_CAPITAL:,.0f}"
            )
        else:
            self._send(
                f"I'm not sure how to answer that, but here's what I know:\n\n"
                f"Market: {regime}\n"
                f"Strategy: {engine}\n"
                f"Trades today: {trades}\n"
                f"P&L: ₹{pnl:+,.2f}\n"
                f"Capital: ₹{config.TOTAL_CAPITAL:,}\n\n"
                f"Try /why, /status, /pnl, or /regime for more details."
            )

    def _cmd_explain(self, text):
        """Explain trading terms in plain English."""
        term = text.replace("/explain", "").strip().lower()
        if not term:
            self._send(
                "Tell me a term to explain! Examples:\n"
                "/explain PF\n"
                "/explain VIX\n"
                "/explain stop loss\n"
                "/explain RSI"
            )
            return

        explanations = {
            "pf": (
                "<b>Profit Factor (PF)</b>\n"
                "= Total money won ÷ Total money lost.\n"
                "PF > 1 means you're making money overall.\n"
                "PF of 1.5 = for every ₹1 lost, you make ₹1.50."
            ),
            "profit factor": (
                "<b>Profit Factor (PF)</b>\n"
                "= Total money won ÷ Total money lost.\n"
                "PF > 1 means you're making money overall.\n"
                "PF of 1.5 = for every ₹1 lost, you make ₹1.50."
            ),
            "vix": (
                "<b>VIX (Volatility Index)</b>\n"
                "Think of it as the market's 'fear meter'.\n"
                "Low (below 15): Market is calm, small moves.\n"
                "Medium (15-22): Normal conditions.\n"
                "High (above 22): Market is nervous, big swings.\n"
                "Above 30: Panic! Very risky to trade."
            ),
            "stop loss": (
                "<b>Stop Loss (SL)</b>\n"
                "A safety net. If the price goes against you,\n"
                "the bot automatically sells to limit your loss.\n"
                "Example: Buy at ₹100, SL at ₹85 = max loss is ₹15."
            ),
            "sl": (
                "<b>Stop Loss (SL)</b>\n"
                "A safety net. If the price goes against you,\n"
                "the bot automatically sells to limit your loss.\n"
                "Example: Buy at ₹100, SL at ₹85 = max loss is ₹15."
            ),
            "rsi": (
                "<b>RSI (Relative Strength Index)</b>\n"
                "Measures if something is 'overbought' or 'oversold'.\n"
                "Below 30: Oversold — price dropped too much, may bounce.\n"
                "Above 70: Overbought — price rose too much, may drop.\n"
                "The bot uses this to time entries."
            ),
            "vwap": (
                "<b>VWAP (Volume Weighted Average Price)</b>\n"
                "The 'fair price' of the day based on volume.\n"
                "If price is below VWAP: it's cheap relative to average.\n"
                "If price is above VWAP: it's expensive relative to average.\n"
                "Mean reversion trades target a return to VWAP."
            ),
            "ce": (
                "<b>CE (Call Option)</b>\n"
                "A bet that the market will go UP.\n"
                "You buy a CE when you're bullish.\n"
                "If Nifty goes up, your CE makes money."
            ),
            "pe": (
                "<b>PE (Put Option)</b>\n"
                "A bet that the market will go DOWN.\n"
                "You buy a PE when you're bearish.\n"
                "If Nifty goes down, your PE makes money."
            ),
            "oi": (
                "<b>OI (Open Interest)</b>\n"
                "How many option contracts are currently active.\n"
                "High OI = lots of traders are interested = good liquidity.\n"
                "Low OI = risky, hard to buy/sell at fair prices."
            ),
            "fii": (
                "<b>FII (Foreign Institutional Investors)</b>\n"
                "Big foreign funds that invest in Indian markets.\n"
                "When FII buy: usually bullish for market.\n"
                "When FII sell: usually bearish pressure."
            ),
            "dii": (
                "<b>DII (Domestic Institutional Investors)</b>\n"
                "Indian mutual funds, insurance companies, etc.\n"
                "They often buy when FII sell (and vice versa).\n"
                "DII buying supports the market during sell-offs."
            ),
            "regime": (
                "<b>Market Regime</b>\n"
                "The 'type' of market right now:\n"
                "TRENDING: Moving steadily in one direction.\n"
                "RANGING: Bouncing sideways between levels.\n"
                "VOLATILE: Big unpredictable swings.\n"
                "Different strategies work for each type."
            ),
            "paper trade": (
                "<b>Paper Trading</b>\n"
                "Practice mode! The bot does everything except\n"
                "place real orders. You see what would happen\n"
                "without risking real money. Great for testing."
            ),
            "trailing stop": (
                "<b>Trailing Stop</b>\n"
                "A stop loss that moves UP with the price.\n"
                "It locks in profits as the trade goes your way.\n"
                "If price drops back, it sells automatically."
            ),
        }

        # Try to find a match
        reply = explanations.get(term)
        if not reply:
            # Try partial matching
            for key, val in explanations.items():
                if term in key or key in term:
                    reply = val
                    break

        if reply:
            self._send(f"📚 {reply}")
        else:
            self._send(
                f"I don't have an explanation for '{term}' yet.\n"
                f"Try: PF, VIX, RSI, VWAP, stop loss, CE, PE, OI, FII, DII, regime, paper trade, trailing stop"
            )

    def _cmd_help(self):
        self._send(
            "📋 <b>Commands — talk to your bot!</b>\n\n"
            "<b>Market info:</b>\n"
            "/status — Is the bot running? What's it doing?\n"
            "/pnl — How much did I make/lose today?\n"
            "/feeds — What are big investors doing?\n"
            "/regime — What type of market is it today?\n\n"
            "<b>Actions:</b>\n"
            "/signal — Force a market scan now\n"
            "/stop — Pause the bot\n"
            "/resume — Resume the bot\n\n"
            "<b>Learn & understand:</b>\n"
            "/why — Why did you do (or not do) that?\n"
            "/ask [question] — Ask me anything\n"
            "/explain [term] — What does this term mean?\n"
            "/settings — Show my current settings\n"
            "/health — Is everything working?\n"
        )
