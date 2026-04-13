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
        """Send a trading signal alert."""

        if signal.action == "HOLD":
            return False  # Don't spam HOLD signals

        action_emoji = "🟢" if signal.action == "BUY_CE" else "🔴"
        action_text = "BUY CALL (CE)" if signal.action == "BUY_CE" else "BUY PUT (PE)"

        # Confidence bar
        filled = int(signal.confidence / 10)
        conf_bar = "█" * filled + "░" * (10 - filled)

        # Risk amount for ₹10K capital
        risk_per_lot = abs(signal.entry_price - signal.stop_loss) * 25  # Nifty lot
        max_lots = max(1, int(config.MAX_RISK_PER_TRADE / risk_per_lot)) if risk_per_lot > 0 else 1

        reasons_text = "\n".join([f"  • {r}" for r in signal.reasons[:5]])

        msg = f"""
{action_emoji} <b>GX TRADEINTEL SIGNAL</b> {action_emoji}

<b>🎯 {action_text}</b>
<b>Instrument:</b> <code>{signal.instrument}</code>
<b>Timeframe:</b> 5 min

━━━━━━━━━━━━━━━━━━━━

<b>📍 Entry:</b>  <code>₹{signal.entry_price:,.2f}</code>
<b>🛑 Stop Loss:</b>  <code>₹{signal.stop_loss:,.2f}</code>
<b>🎯 Target:</b>  <code>₹{signal.target:,.2f}</code>
<b>📊 R:R Ratio:</b>  <code>{signal.risk_reward}x</code>

━━━━━━━━━━━━━━━━━━━━

<b>Confidence:</b> [{conf_bar}] {signal.confidence}%

<b>Reasons:</b>
{reasons_text}

<b>Position Size:</b> {max_lots} lot(s)
<b>Max Risk:</b> ₹{config.MAX_RISK_PER_TRADE:,.0f}

⏰ {datetime.now().strftime('%H:%M:%S IST')}
{'📝 PAPER TRADE' if config.PAPER_TRADE else '⚡ LIVE TRADE'}
"""
        return self.send(msg.strip())

    # ── Morning Briefing ────────────────────────

    def send_morning_briefing(
        self,
        nifty_price: float,
        sentiment: dict,
        high_impact_news: list,
    ) -> bool:
        """Send pre-market morning briefing."""

        sentiment_emoji = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡"}.get(
            sentiment.get("label", "NEUTRAL"), "🟡"
        )

        news_text = ""
        for n in high_impact_news[:5]:
            s_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}.get(n.sentiment, "➖")
            news_text += f"  {s_emoji} {n.title[:60]}...\n"

        if not news_text:
            news_text = "  No high-impact news detected\n"

        msg = f"""
☀️ <b>GX TRADEINTEL — MORNING BRIEFING</b>
📅 {datetime.now().strftime('%A, %d %B %Y')}

━━━━━━━━━━━━━━━━━━━━

<b>📊 NIFTY 50:</b> <code>₹{nifty_price:,.2f}</code>

<b>{sentiment_emoji} Market Sentiment:</b> <code>{sentiment.get('label', 'N/A')}</code>
  Score: {sentiment.get('score', 0):.2f}
  Bullish: {sentiment.get('bullish', 0)} | Bearish: {sentiment.get('bearish', 0)} | Neutral: {sentiment.get('neutral', 0)}

<b>🔥 Key News:</b>
{news_text}
<b>💰 Capital:</b> ₹{config.TOTAL_CAPITAL:,}
<b>⚠️ Max Risk/Trade:</b> ₹{config.MAX_RISK_PER_TRADE:,.0f}
<b>🎯 Strategy:</b> RSI + VWAP + EMA Confluence

━━━━━━━━━━━━━━━━━━━━
{'📝 PAPER MODE — No real orders' if config.PAPER_TRADE else '⚡ LIVE MODE — Real orders enabled'}
"""
        return self.send(msg.strip())

    # ── Trade Execution Alert ───────────────────

    def send_trade_entry(
        self, symbol: str, action: str, qty: int, price: float, order_id: str
    ) -> bool:
        """Alert when a trade is entered."""
        emoji = "🟢" if "CE" in action or "BUY" in action else "🔴"
        msg = f"""
{emoji} <b>TRADE ENTERED</b>

<b>Symbol:</b> <code>{symbol}</code>
<b>Action:</b> {action}
<b>Qty:</b> {qty}
<b>Price:</b> <code>₹{price:,.2f}</code>
<b>Order ID:</b> <code>{order_id}</code>
⏰ {datetime.now().strftime('%H:%M:%S IST')}
"""
        return self.send(msg.strip())

    def send_trade_exit(
        self, symbol: str, entry_price: float, exit_price: float, qty: int, pnl: float
    ) -> bool:
        """Alert when a trade is exited."""
        emoji = "💰" if pnl > 0 else "💸"
        pnl_text = f"+₹{pnl:,.2f}" if pnl > 0 else f"-₹{abs(pnl):,.2f}"
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        msg = f"""
{emoji} <b>TRADE CLOSED</b>

<b>Symbol:</b> <code>{symbol}</code>
<b>Entry:</b> <code>₹{entry_price:,.2f}</code>
<b>Exit:</b> <code>₹{exit_price:,.2f}</code>
<b>Qty:</b> {qty}

<b>P&L:</b> <code>{pnl_text}</code> ({pnl_pct:+.1f}%)
⏰ {datetime.now().strftime('%H:%M:%S IST')}
"""
        return self.send(msg.strip())

    # ── Daily Summary ───────────────────────────

    def send_daily_summary(
        self, total_trades: int, wins: int, losses: int, total_pnl: float
    ) -> bool:
        """End-of-day P&L summary."""
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        emoji = "🏆" if total_pnl > 0 else "📉"
        pnl_text = f"+₹{total_pnl:,.2f}" if total_pnl > 0 else f"-₹{abs(total_pnl):,.2f}"

        msg = f"""
{emoji} <b>DAILY SUMMARY — {datetime.now().strftime('%d %b %Y')}</b>

━━━━━━━━━━━━━━━━━━━━
<b>Trades:</b> {total_trades}
<b>Wins:</b> {wins} | <b>Losses:</b> {losses}
<b>Win Rate:</b> {win_rate:.0f}%

<b>Net P&L:</b> <code>{pnl_text}</code>
<b>Capital:</b> <code>₹{config.TOTAL_CAPITAL + total_pnl:,.2f}</code>
━━━━━━━━━━━━━━━━━━━━

See you tomorrow! 🌙
"""
        return self.send(msg.strip())

    # ── News Alert ──────────────────────────────

    def send_news_alert(self, title: str, sentiment: str, impact: str, source: str) -> bool:
        """Alert for high-impact news."""
        emoji = {"bullish": "📈", "bearish": "📉", "neutral": "📰"}.get(sentiment, "📰")
        impact_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}.get(impact, "⚪")

        msg = f"""
{emoji} <b>NEWS ALERT</b> {impact_emoji} {impact}

{title}

<b>Sentiment:</b> {sentiment.upper()}
<b>Source:</b> {source}
⏰ {datetime.now().strftime('%H:%M:%S IST')}
"""
        return self.send(msg.strip())
