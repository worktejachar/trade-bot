# -*- coding: utf-8 -*-
"""
GX TradeIntel v5 — AI Conductor
==================================
Source: ai-conductor skill
Uses Claude API to decide: MOMENTUM / MEAN_REVERSION / SCALPER / NO_TRADE
Falls back to rule-based when API unavailable.
Cost: ~₹1-2/day (negligible vs edge gained)
"""
import logging
import json
import re
from datetime import datetime

import requests
import config

logger = logging.getLogger("GXTradeIntel.Conductor")

SYSTEM_PROMPT = """You are a quantitative trading strategist for the Indian stock market (NSE).
Analyze the data and pick ONE strategy for today.

Engines:
1. MOMENTUM — trending markets, buy options in trend direction on pullbacks. Win rate ~62%.
2. MEAN_REVERSION — ranging markets, buy options when price deviates from VWAP/mean. Win rate ~72%.
3. SCALPER — volatile markets, quick ORB breakouts. Win rate ~60%.
4. NO_TRADE — unclear conditions. Cash is a position.

Rules:
- Pick exactly ONE.
- Confidence 0-100. Below 60 = NO_TRADE.
- Be conservative. Missing a trade > forcing one.

Respond ONLY in JSON:
{"strategy":"...","direction":"BULLISH|BEARISH|NEUTRAL","confidence":0-100,"reasoning":"...","key_factor":"...","risk_note":"..."}"""


def call_conductor(indicators: dict, regime: dict, macro: dict, news: dict) -> dict:
    """Call Claude API for strategy decision."""
    if not config.CONDUCTOR["use_ai"] or not config.ANTHROPIC_API_KEY or len(config.ANTHROPIC_API_KEY) < 10 or config.ANTHROPIC_API_KEY.startswith("YOUR"):
        return fallback_conductor(regime)

    data_package = _build_input(indicators, regime, macro, news)

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json",
                     "x-api-key": config.ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01"},
            json={"model": config.CONDUCTOR["model"],
                  "max_tokens": 400,
                  "system": SYSTEM_PROMPT,
                  "messages": [{"role": "user", "content": data_package}]},
            timeout=30,
        )

        if resp.status_code != 200:
            logger.warning(f"Conductor API {resp.status_code}, using fallback")
            return fallback_conductor(regime)

        text = resp.json()["content"][0]["text"]
        text = re.sub(r"```json?\n?", "", text).rstrip("`").strip()
        decision = json.loads(text)

        valid = ["MOMENTUM", "MEAN_REVERSION", "SCALPER", "NO_TRADE"]
        if decision.get("strategy") not in valid:
            decision["strategy"] = "NO_TRADE"
        if decision.get("confidence", 0) < config.CONDUCTOR["min_conductor_confidence"]:
            decision["strategy"] = "NO_TRADE"

        decision["source"] = "AI"
        logger.info(f"🧠 CONDUCTOR (AI): {decision['strategy']} | Conf: {decision['confidence']}% | {decision.get('reasoning', '')[:80]}")
        return decision

    except Exception as e:
        logger.warning(f"Conductor error: {e}, using fallback")
        return fallback_conductor(regime)


def fallback_conductor(regime: dict) -> dict:
    """Rule-based fallback using regime detection scores."""
    r = regime.get("regime", "UNCLEAR")
    d = regime.get("direction", "NONE")
    c = regime.get("confidence", 0)

    mapping = {
        "TRENDING": ("MOMENTUM", d),
        "RANGING": ("MEAN_REVERSION", "NEUTRAL"),
        "VOLATILE": ("SCALPER", d if d != "NONE" else "NEUTRAL"),
        "UNCLEAR": ("NO_TRADE", "NEUTRAL"),
    }

    strategy, direction = mapping.get(r, ("NO_TRADE", "NEUTRAL"))
    if c < config.REGIME["min_regime_confidence"]:
        strategy = "NO_TRADE"

    result = {
        "strategy": strategy,
        "direction": direction,
        "confidence": c,
        "reasoning": f"Rule-based: regime={r}, confidence={c}%",
        "key_factor": f"ADX={regime.get('adx', 'N/A')}, ATR ratio={regime.get('atr_ratio', 'N/A')}",
        "risk_note": "Using algorithmic fallback (no AI)",
        "source": "RULES",
    }
    logger.info(f"🔧 CONDUCTOR (Rules): {strategy} | Conf: {c}% | Regime: {r}")
    return result


def check_news_override(news_items: list, current_strategy: str, direction: str) -> dict:
    """Check if breaking news should override the strategy."""
    if not config.CONDUCTOR["news_override_enabled"]:
        return {"override": False}

    high_impact = [n for n in news_items if getattr(n, "impact", "") == "HIGH"]

    for n in high_impact:
        sentiment = getattr(n, "sentiment", "neutral")
        score = getattr(n, "score", 0)

        if sentiment == "bearish" and score < -0.5 and direction == "BULLISH":
            return {"override": True, "new_strategy": "NO_TRADE",
                    "reason": f"Breaking bearish news contradicts bullish setup: {n.title[:50]}"}

        if sentiment == "bullish" and score > 0.7 and current_strategy == "NO_TRADE":
            return {"override": True, "new_strategy": "MOMENTUM",
                    "reason": f"Strong bullish catalyst: {n.title[:50]}"}

    return {"override": False}


def _build_input(ind, regime, macro, news):
    return f"""MARKET DATA — {datetime.now():%A %d %B %Y %H:%M IST}

TECHNICAL (Nifty 15m):
  Price: ₹{ind.get('price', 0):,.2f} | ADX: {ind.get('adx', 0):.1f} | RSI: {ind.get('rsi', 50):.1f}
  SuperTrend: {'BULL' if ind.get('st_dir', 0) > 0 else 'BEAR'}
  VWAP: {'Above' if ind.get('vs_vwap', 0) > 0 else 'Below'} | EMA: {'Bull' if ind.get('ema_cross', 0) > 0 else 'Bear'}
  BB: {'expanding' if ind.get('bb_expanding', False) else 'contracting'} | Vol: {ind.get('vol_ratio', 1):.1f}x

REGIME (algo): {regime.get('regime', 'N/A')} ({regime.get('confidence', 0)}%)
  Scores: T={regime.get('scores', {}).get('TRENDING', 0)} R={regime.get('scores', {}).get('RANGING', 0)} V={regime.get('scores', {}).get('VOLATILE', 0)}

MACRO: VIX={macro.get('vix', 'N/A')} | FII=₹{macro.get('fii', 0):,.0f}Cr | Crude=${macro.get('crude', 0):.0f}
NEWS: {news.get('label', 'N/A')} (score: {news.get('score', 0):.2f}) | Bull:{news.get('bullish', 0)} Bear:{news.get('bearish', 0)}

Day: {datetime.now():%A} | Capital: ₹10K | Max risk: ₹500

Which strategy should be active?"""
