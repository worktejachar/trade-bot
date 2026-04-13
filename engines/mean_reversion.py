# -*- coding: utf-8 -*-
"""Engine 2: MEAN REVERSION — For RANGING markets. Win rate target: 70-75%, consistent."""
import logging
from dataclasses import dataclass, field
from typing import List
import numpy as np, pandas as pd
import config
from indicators import compute_all, find_support_resistance, detect_candle_patterns

logger = logging.getLogger("GXTradeIntel.MeanRev")

@dataclass
class Signal:
    action: str; direction: str; confidence: int
    entry_price: float; stop_loss: float; target_1: float; target_2: float
    risk_reward: float; instrument: str; engine: str = "MEAN_REVERSION"
    reasons: List[str] = field(default_factory=list)
    rejections: List[str] = field(default_factory=list)
    strike: int = 0; option_type: str = ""; est_premium: float = 0
    @property
    def is_tradeable(self): return self.action != "HOLD" and self.confidence >= config.MEAN_REVERSION["min_confidence"]

def _rsi2(series):
    """Ultra-short RSI(2) for mean reversion extremes."""
    d = series.diff(); g = d.where(d > 0, 0.0); l = -d.where(d < 0, 0.0)
    ag = g.rolling(2).mean(); al = l.rolling(2).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _volume_exhaustion(df, lookback=5):
    """Detect if current move is running out of steam."""
    recent = df.tail(lookback)
    price_dir = recent["close"].iloc[-1] - recent["close"].iloc[0]
    vol_trend = recent["volume"].diff().tail(3).mean()
    if price_dir < 0 and vol_trend < 0: return "BULL_EXHAUST"  # Selling drying up
    if price_dir > 0 and vol_trend < 0: return "BEAR_EXHAUST"  # Buying drying up
    return "NONE"

def _vwap_deviation(price, vwap):
    if vwap == 0: return 0
    return ((price - vwap) / vwap) * 100

def generate(df_5m, df_15m=None, news_score=0, instrument="NIFTY"):
    """Mean reversion signal: buy snap-back to VWAP when price deviates too far."""
    cfg = config.MEAN_REVERSION
    empty = Signal("HOLD", "NEUTRAL", 0, 0, 0, 0, 0, 0, instrument)

    if df_5m is None or len(df_5m) < 50:
        empty.rejections.append("Insufficient data"); return empty

    # Compute indicators (using momentum config structure for compatibility)
    ind_cfg = {"supertrend_period": 10, "supertrend_multiplier": 3, "ema_trend": 50,
               "ema_fast": 9, "ema_slow": 21, "adx_period": 14, "rsi_period": 14,
               "bb_period": cfg["bb_period"], "bb_std": cfg["bb_std"], "obv_lookback": 10}
    df = compute_all(df_5m, ind_cfg)

    # Add RSI(2)
    df["rsi2"] = _rsi2(df["close"])

    L = df.iloc[-1]
    close = L["close"]
    vwap_val = L.get("vwap", close)
    rsi2 = L.get("rsi2", 50)
    bb_pos = L.get("bb_pos", 0.5)
    vol_ratio = L.get("vol_ratio", 1)

    vwap_dev = _vwap_deviation(close, vwap_val)
    vol_exhaust = _volume_exhaustion(df)

    score = 0
    reasons = []
    direction = "NEUTRAL"

    # ── BULLISH MEAN REVERSION (price too low, expect bounce) ──
    bull_score = 0
    bull_reasons = []

    # RSI(2) extreme oversold (+25)
    if rsi2 < cfg["rsi2_oversold"]:
        bull_score += 25
        bull_reasons.append(f"RSI(2) = {rsi2:.1f} (extreme oversold)")
    elif rsi2 < 20:
        bull_score += 15
        bull_reasons.append(f"RSI(2) = {rsi2:.1f} (oversold)")

    # BB lower touch (+20)
    if bb_pos < 0.1:
        bull_score += 20
        bull_reasons.append(f"Price at lower Bollinger Band ({bb_pos:.2f})")
    elif bb_pos < 0.2:
        bull_score += 12
        bull_reasons.append(f"Price near lower BB ({bb_pos:.2f})")

    # VWAP deviation (+15/+20)
    if vwap_dev < -cfg["vwap_strong_deviation"]:
        bull_score += 20
        bull_reasons.append(f"VWAP deviation {vwap_dev:.2f}% (strong oversold)")
    elif vwap_dev < -cfg["vwap_deviation_pct"]:
        bull_score += 15
        bull_reasons.append(f"VWAP deviation {vwap_dev:.2f}%")

    # Volume exhaustion (+15)
    if vol_exhaust == "BULL_EXHAUST":
        bull_score += 15
        bull_reasons.append("Selling volume exhausting (bullish)")

    # Candle pattern (+10)
    if L.get("candle_bull_score", 0) >= 3:
        bull_score += 10
        bull_reasons.append("Bullish candle pattern")

    # S/R proximity (+10)
    sr_levels = find_support_resistance(df)
    near_support = any(abs(close - s["level"]) / close * 100 < 0.3 for s in sr_levels)
    if near_support:
        bull_score += 10
        bull_reasons.append("Near support level")

    # ── BEARISH MEAN REVERSION (price too high, expect pullback) ──
    bear_score = 0
    bear_reasons = []

    if rsi2 > cfg["rsi2_overbought"]:
        bear_score += 25
        bear_reasons.append(f"RSI(2) = {rsi2:.1f} (extreme overbought)")
    elif rsi2 > 80:
        bear_score += 15
        bear_reasons.append(f"RSI(2) = {rsi2:.1f} (overbought)")

    if bb_pos > 0.9:
        bear_score += 20
        bear_reasons.append(f"Price at upper BB ({bb_pos:.2f})")
    elif bb_pos > 0.8:
        bear_score += 12

    if vwap_dev > cfg["vwap_strong_deviation"]:
        bear_score += 20
        bear_reasons.append(f"VWAP deviation +{vwap_dev:.2f}% (strong overbought)")
    elif vwap_dev > cfg["vwap_deviation_pct"]:
        bear_score += 15

    if vol_exhaust == "BEAR_EXHAUST":
        bear_score += 15
        bear_reasons.append("Buying volume exhausting")

    if L.get("candle_bear_score", 0) >= 3:
        bear_score += 10
        bear_reasons.append("Bearish candle pattern")

    near_resistance = any(abs(close - s["level"]) / close * 100 < 0.3 for s in sr_levels)
    if near_resistance:
        bear_score += 10
        bear_reasons.append("Near resistance level")

    # ── Pick stronger direction ──
    if bull_score > bear_score and bull_score >= cfg["min_confidence"]:
        direction = "BULLISH"
        score = bull_score
        reasons = bull_reasons
        action = "BUY_CE"
    elif bear_score > bull_score and bear_score >= cfg["min_confidence"]:
        direction = "BEARISH"
        score = bear_score
        reasons = bear_reasons
        action = "BUY_PE"
    else:
        empty.rejections.append(f"Mean rev scores too low: bull={bull_score} bear={bear_score}")
        return empty

    # Time bonus
    from datetime import datetime
    now = datetime.now().time()
    if config.GOLDEN_START <= now <= config.GOLDEN_END:
        score = min(100, score + 5)
        reasons.append("Golden hours")

    # Clamp
    score = min(100, max(0, score))
    if score < cfg["min_confidence"]:
        action = "HOLD"

    # Targets: reversion to VWAP
    atr = L.get("atr", close * 0.003)
    if direction == "BULLISH":
        sl = close - 1.2 * atr
        t1 = vwap_val  # Natural target = VWAP
        t2 = close + 1.5 * atr
    else:
        sl = close + 1.2 * atr
        t1 = vwap_val
        t2 = close - 1.5 * atr

    rr = round(abs(t1 - close) / abs(close - sl), 2) if abs(close - sl) > 0 else 0

    sg = config.INSTRUMENTS.get(instrument, {}).get("strike_gap", 50)
    strike = round(close / sg) * sg
    ot = "CE" if direction == "BULLISH" else "PE"

    return Signal(action, direction, score, round(close, 2), round(sl, 2), round(t1, 2),
                  round(t2, 2), rr, instrument, "MEAN_REVERSION", reasons, [], strike, ot)
