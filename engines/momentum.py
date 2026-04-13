# -*- coding: utf-8 -*-
"""Engine 1: MOMENTUM — For TRENDING markets. Win rate target: 60-65%, high profit."""
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np, pandas as pd
import config
from indicators import compute_all, find_support_resistance

logger = logging.getLogger("GXTradeIntel.Momentum")

@dataclass
class Signal:
    action: str  # BUY_CE, BUY_PE, HOLD
    direction: str
    confidence: int
    entry_price: float; stop_loss: float; target_1: float; target_2: float
    risk_reward: float; instrument: str; engine: str = "MOMENTUM"
    reasons: List[str] = field(default_factory=list)
    rejections: List[str] = field(default_factory=list)
    strike: int = 0; option_type: str = ""; est_premium: float = 0
    @property
    def is_tradeable(self): return self.action != "HOLD" and self.confidence >= config.MOMENTUM["min_confidence"]

def generate(df_5m, df_15m=None, news_score=0, instrument="NIFTY"):
    """Momentum signal: trend-following with pullback entry."""
    cfg = config.MOMENTUM
    empty = Signal("HOLD", "NEUTRAL", 0, 0, 0, 0, 0, 0, instrument)

    if df_5m is None or len(df_5m) < 50:
        empty.rejections.append("Insufficient data"); return empty

    df = compute_all(df_5m, {"supertrend_period": cfg["supertrend_period"], "supertrend_multiplier": cfg["supertrend_mult"],
                              "ema_trend": cfg["ema_trend"], "ema_fast": cfg["ema_fast"], "ema_slow": cfg["ema_slow"],
                              "adx_period": 14, "rsi_period": cfg["rsi_period"], "bb_period": cfg["bb_period"],
                              "bb_std": cfg["bb_std"], "obv_lookback": 10})
    L = df.iloc[-1]; P = df.iloc[-2]

    # Tier 1: ALL trend indicators must agree
    adx = L.get("adx", 0)
    if adx < cfg["adx_min"]:
        empty.rejections.append(f"ADX {adx:.1f} < {cfg['adx_min']}"); return empty

    st = L.get("st_direction", 0); ema50 = L.get("price_vs_ema50", 0); vw = L.get("price_vs_vwap", 0)
    bulls = sum(1 for x in [st, ema50, vw] if x > 0)
    bears = sum(1 for x in [st, ema50, vw] if x < 0)

    if bulls == 3: trend, t1_score = "BULLISH", 30
    elif bears == 3: trend, t1_score = "BEARISH", 30
    else: empty.rejections.append(f"Trend split {bulls}B/{bears}S"); return empty

    # Tier 2: Entry (need ALL 4)
    t2 = 0; t2r = []
    rsi = L.get("rsi", 50)
    if (trend == "BULLISH" and rsi < 45) or (trend == "BEARISH" and rsi > 55): t2 += 1; t2r.append(f"RSI {rsi:.0f}")
    ec = L.get("ema_cross", 0)
    if (trend == "BULLISH" and ec > 0) or (trend == "BEARISH" and ec < 0): t2 += 1; t2r.append("EMA cross aligned")
    md = L.get("macd_dir", 0)
    if (trend == "BULLISH" and md > 0) or (trend == "BEARISH" and md < 0): t2 += 1; t2r.append("MACD aligned")
    bp = L.get("bb_pos", 0.5)
    if (trend == "BULLISH" and bp < 0.3) or (trend == "BEARISH" and bp > 0.7): t2 += 1; t2r.append(f"BB {bp:.2f}")

    if t2 < 3: empty.rejections.append(f"Tier2 {t2}/4"); return empty
    t2_score = 25 if t2 == 4 else 18

    # Tier 3: Volume
    vr = L.get("vol_ratio", 1)
    if vr < 1.5: empty.rejections.append(f"Vol {vr:.1f}x low"); return empty
    t3_score = 15 if vr >= 2.0 else 10

    # Tier 4: 15m alignment
    t4_score = 5
    if df_15m is not None and len(df_15m) >= 50 and cfg["require_15m_align"]:
        df15 = compute_all(df_15m, {"supertrend_period": cfg["supertrend_period"], "supertrend_multiplier": cfg["supertrend_mult"],
                                     "ema_trend": cfg["ema_trend"], "ema_fast": cfg["ema_fast"], "ema_slow": cfg["ema_slow"],
                                     "adx_period": 14, "rsi_period": cfg["rsi_period"], "bb_period": cfg["bb_period"],
                                     "bb_std": cfg["bb_std"], "obv_lookback": 10})
        l15 = df15.iloc[-1]
        if (trend == "BULLISH" and l15.get("st_direction", 0) > 0 and l15.get("price_vs_ema50", 0) > 0) or \
           (trend == "BEARISH" and l15.get("st_direction", 0) < 0 and l15.get("price_vs_ema50", 0) < 0):
            t4_score = 15
        else:
            t4_score = 0; t2r.append("15m conflicts")

    # News
    ns = 5 if (news_score > 0.2 and trend == "BULLISH") or (news_score < -0.2 and trend == "BEARISH") else -5 if abs(news_score) > 0.2 else 0

    total = max(0, min(100, t1_score + t2_score + t3_score + t4_score + ns))
    action = "BUY_CE" if trend == "BULLISH" else "BUY_PE"
    if total < cfg["min_confidence"]: action = "HOLD"

    close = L["close"]; atr = L.get("atr", close * 0.005)
    if trend == "BULLISH": sl = close - 1.5*atr; t1 = close + 2*atr; t2_p = close + 3*atr
    else: sl = close + 1.5*atr; t1 = close - 2*atr; t2_p = close - 3*atr
    rr = round(abs(t1 - close) / abs(close - sl), 2) if abs(close - sl) > 0 else 0

    # Strike
    sg = config.INSTRUMENTS.get(instrument, {}).get("strike_gap", 50)
    strike = round(close / sg) * sg
    ot = "CE" if trend == "BULLISH" else "PE"

    reasons = [f"ADX {adx:.0f}", f"Trend: {trend}"] + t2r + [f"Vol {vr:.1f}x"]
    return Signal(action, trend, total, round(close, 2), round(sl, 2), round(t1, 2), round(t2_p, 2),
                  rr, instrument, "MOMENTUM", reasons, [], strike, ot)
