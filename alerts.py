# -*- coding: utf-8 -*-
"""
GX TradeIntel - Telegram Alert System
=======================================
Sends formatted trading alerts to Telegram:
- Signal alerts (BUY CE/PE with entry/SL/target)
- Morning market briefing
- Position updates (entry, exit, P&L)
- News alerts (high impact only)
- Daily P&L summary
"""

import logging
from datetime import datetime
from typing import Optional

import requests

import config

logger = logging.getLogger("GXTradeIntel.Telegram")


class TelegramAlerts:
    """Send formatted trading alerts via Telegram."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = self.token != "YOUR_BOT_TOKEN" and self.chat_id != "YOUR_CHAT_ID"

        if not self.enabled:
            logger.warning("⚠️  Telegram not configured — alerts will print to console only")

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send message to Telegram."""
        # Always log to console
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        plain = plain.replace("<code>", "").replace("</code>", "").replace("<pre>", "").replace("</pre>", "")
        logger.info(f"📱 ALERT: {plain[:200]}...")

        if not self.enabled:
            return False

        try:
            url = f"{self.BASE_URL.format(token=self.token)}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }, timeout=10)

            if resp.status_code == 200:
                return True
            else:
                logger.warning(f"Telegram send failed: {resp.status_code} - {resp.text}")
                return False

        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    # ── Signal Alert ────────────────────────────

    def send_signal(self, signal) -> bool:
        """Send a trading signal alert in plain English."""

        if signal.action == "HOLD":
            return False  # Don't spam HOLD signals

        if signal.action == "BUY_CE":
            direction_desc = "CALL option (betting market goes UP)"
        else:
            direction_desc = "PUT option (betting market goes DOWN)"

        # Risk calculation
        risk_per_unit = abs(signal.entry_price - signal.stop_loss)
        risk_per_lot = risk_per_unit * 25  # Nifty lot
        max_lots = max(1, int(config.MAX_RISK_PER_TRADE / risk_per_lot)) if risk_per_lot > 0 else 1
        total_risk = risk_per_unit * max_lots * 25

        # Confidence description
        if signal.confidence >= 85:
            conf_desc = "very strong signal"
        elif signal.confidence >= 70:
            conf_desc = "strong signal"
        elif signal.confidence >= 55:
            conf_desc = "moderate signal"
        else:
            conf_desc = "weak signal"

        # Plain English reasons
        reasons_text = "\n".join([f"  - {r}" for r in signal.reasons[:5]])

        msg = f"""
🔔 <b>TRADE ALERT</b>

I'm buying a {signal.instrument} <b>{direction_desc}</b>.

<b>Strike:</b> {signal.instrument} | <b>Price:</b> ₹{signal.entry_price:,.2f} per unit
<b>If I'm wrong:</b> I'll exit at ₹{signal.stop_loss:,.2f} (lose ₹{risk_per_unit:,.2f} per unit)
<b>If I'm right:</b> Target ₹{signal.target:,.2f} (R:R {signal.risk_reward}x)

<b>Confidence:</b> {signal.confidence}% ({conf_desc})
<b>Position:</b> {max_lots} lot(s) | Max risk: ₹{config.MAX_RISK_PER_TRADE:,.0f}

<b>Why this trade:</b>
{reasons_text}

⏰ {datetime.now().strftime('%H:%M:%S IST')}
{'📝 PAPER TRADE (no real money)' if config.PAPER_TRADE else '⚡ LIVE TRADE (real money)'}
"""
        return self.send(msg.strip())

    # ── Morning Briefing ────────────────────────

    def send_morning_briefing(
        self,
        nifty_price: float,
        sentiment: dict,
        high_impact_news: list,
    ) -> bool:
        """Send pre-market morning briefing in plain English."""

        label = sentiment.get("label", "NEUTRAL")
        score = sentiment.get("score", 0)
        bullish_count = sentiment.get("bullish", 0)
        bearish_count = sentiment.get("bearish", 0)
        neutral_count = sentiment.get("neutral", 0)

        # Plain English sentiment
        if label == "BULLISH":
            mood = "positive — more good news than bad"
            emoji = "🟢"
        elif label == "BEARISH":
            mood = "negative — more bad news than good"
            emoji = "🔴"
        else:
            mood = "mixed — no clear direction from news"
            emoji = "🟡"

        news_text = ""
        for n in high_impact_news[:5]:
            s_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}.get(n.sentiment, "➖")
            news_text += f"  {s_emoji} {n.title[:60]}...\n"

        if not news_text:
            news_text = "  Nothing major in the news today.\n"

        msg = f"""
☀️ <b>Good Morning! Here's your market update.</b>
📅 {datetime.now().strftime('%A, %d %B %Y')}

━━━━━━━━━━━━━━━━━━━━

<b>Nifty 50 is at ₹{nifty_price:,.2f}</b>

{emoji} <b>Today's mood:</b> {mood}
  ({bullish_count} positive news, {bearish_count} negative, {neutral_count} neutral)

<b>Key news today:</b>
{news_text}
<b>Your capital:</b> ₹{config.TOTAL_CAPITAL:,}
<b>Max I'll risk per trade:</b> ₹{config.MAX_RISK_PER_TRADE:,.0f}
<b>Strategy:</b> I'll watch for price + volume patterns and trade when conditions align.

━━━━━━━━━━━━━━━━━━━━
{'📝 PAPER MODE — just practicing, no real money at risk' if config.PAPER_TRADE else '⚡ LIVE MODE — real orders will be placed'}
"""
        return self.send(msg.strip())

    # ── Trade Execution Alert ───────────────────

    def send_trade_entry(
        self, symbol: str, action: str, qty: int, price: float, order_id: str
    ) -> bool:
        """Alert when a trade is entered."""
        if "CE" in action or "BUY" in action:
            direction = "expecting the market to go UP"
        else:
            direction = "expecting the market to go DOWN"

        msg = f"""
🟢 <b>I just entered a trade!</b>

<b>What:</b> {symbol} — {direction}
<b>Quantity:</b> {qty} units
<b>Bought at:</b> ₹{price:,.2f}
<b>Order ID:</b> <code>{order_id}</code>
⏰ {datetime.now().strftime('%H:%M:%S IST')}
"""
        return self.send(msg.strip())

    def send_trade_exit(
        self, symbol: str, entry_price: float, exit_price: float, qty: int, pnl: float
    ) -> bool:
        """Alert when a trade is exited."""
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        if pnl > 0:
            result = f"Made ₹{pnl:,.2f} profit ({pnl_pct:+.1f}%)"
            emoji = "💰"
        elif pnl < 0:
            result = f"Lost ₹{abs(pnl):,.2f} ({pnl_pct:+.1f}%)"
            emoji = "💸"
        else:
            result = "Broke even (no profit, no loss)"
            emoji = "↔️"

        msg = f"""
{emoji} <b>Trade closed!</b>

<b>What:</b> {symbol}
<b>Bought at:</b> ₹{entry_price:,.2f} → <b>Sold at:</b> ₹{exit_price:,.2f}
<b>Quantity:</b> {qty} units
<b>Result:</b> {result}
⏰ {datetime.now().strftime('%H:%M:%S IST')}
"""
        return self.send(msg.strip())

    # ── Daily Summary ───────────────────────────

    def send_daily_summary(
        self, total_trades: int, wins: int, losses: int, total_pnl: float
    ) -> bool:
        """End-of-day P&L summary in plain English."""
        capital_after = config.TOTAL_CAPITAL + total_pnl

        if total_trades == 0:
            msg = f"""
🌙 <b>Today's Result — {datetime.now().strftime('%d %b %Y')}</b>

No trades taken today — market didn't give a clear opportunity.
Your capital: ₹{config.TOTAL_CAPITAL:,.2f} (unchanged).
Tomorrow we try again. Good night!
"""
        elif total_pnl > 0:
            msg = f"""
🏆 <b>Today's Result — {datetime.now().strftime('%d %b %Y')}</b>

Good day! Made a profit.

Trades taken: {total_trades}
Won {wins}, lost {losses} ({(wins / total_trades * 100):.0f}% win rate)
<b>Profit today: +₹{total_pnl:,.2f}</b>
Your capital: ₹{capital_after:,.2f}

See you tomorrow! 🌙
"""
        elif total_pnl < 0:
            msg = f"""
📉 <b>Today's Result — {datetime.now().strftime('%d %b %Y')}</b>

Tough day. Took a small loss.

Trades taken: {total_trades}
Won {wins}, lost {losses} ({(wins / total_trades * 100):.0f}% win rate)
<b>Loss today: -₹{abs(total_pnl):,.2f}</b>
Your capital: ₹{capital_after:,.2f}

Losses happen — it's part of trading. We stick to the plan. 🌙
"""
        else:
            msg = f"""
↔️ <b>Today's Result — {datetime.now().strftime('%d %b %Y')}</b>

Broke even today — no profit, no loss.

Trades taken: {total_trades}
Won {wins}, lost {losses}
Your capital: ₹{capital_after:,.2f} (unchanged)

See you tomorrow! 🌙
"""
        return self.send(msg.strip())

    # ── News Alert ──────────────────────────────

    def send_news_alert(self, title: str, sentiment: str, impact: str, source: str) -> bool:
        """Alert for high-impact news in plain English."""
        if sentiment == "bullish":
            mood = "This is good for the market (prices may go up)."
        elif sentiment == "bearish":
            mood = "This could hurt the market (prices may drop)."
        else:
            mood = "This probably won't move the market much."

        if impact == "HIGH":
            urgency = "⚠️ High impact — this could cause big moves!"
        elif impact == "MEDIUM":
            urgency = "Medium impact — worth keeping an eye on."
        else:
            urgency = "Low impact — unlikely to affect trading."

        msg = f"""
📰 <b>News Update</b>

{title}

{mood}
{urgency}
Source: {source}
⏰ {datetime.now().strftime('%H:%M:%S IST')}
"""
        return self.send(msg.strip())
