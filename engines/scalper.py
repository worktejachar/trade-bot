# -*- coding: utf-8 -*-
"""Engine 3: SCALPER — For VOLATILE markets. Quick ORB breakouts + VWAP bounces."""
import logging
from dataclasses import dataclass, field
from typing import List
import config
from indicators import compute_all, calculate_orb

logger = logging.getLogger("GXTradeIntel.Scalper")

@dataclass
class Signal:
    action: str; direction: str; confidence: int
    entry_price: float; stop_loss: float; target_1: float; target_2: float
    risk_reward: float; instrument: str; engine: str = "SCALPER"
    reasons: List[str] = field(default_factory=list)
    rejections: List[str] = field(default_factory=list)
    strike: int = 0; option_type: str = ""; est_premium: float = 0
    @property
    def is_tradeable(self): return self.action != "HOLD" and self.confidence >= config.SCALPER["min_confidence"]

def generate(df_5m, df_15m=None, news_score=0, instrument="NIFTY"):
    """Scalper: ORB breakout in volatile markets."""
    cfg = config.SCALPER
    empty = Signal("HOLD", "NEUTRAL", 0, 0, 0, 0, 0, 0, instrument)

    if df_5m is None or len(df_5m) < 20:
        empty.rejections.append("Insufficient data"); return empty

    ind_cfg = {"supertrend_period": 10, "supertrend_multiplier": 3, "ema_trend": 50,
               "ema_fast": 9, "ema_slow": 21, "adx_period": 14, "rsi_period": 14,
               "bb_period": 20, "bb_std": 2.0, "obv_lookback": 10}
    df = compute_all(df_5m, ind_cfg)
    L = df.iloc[-1]
    close = L["close"]

    # ORB calculation
    orb = calculate_orb(df, cfg["orb_minutes"])
    if not orb or not orb.get("is_valid", False):
        empty.rejections.append("ORB invalid or range too wide"); return empty

    score = 0; reasons = []; direction = "NEUTRAL"; action = "HOLD"

    orb_h = orb["high"]; orb_l = orb["low"]; orb_range = orb["range"]

    if orb_range > cfg["orb_max_range"]:
        empty.rejections.append(f"ORB range {orb_range:.0f} > {cfg['orb_max_range']}"); return empty

    # Breakout above ORB high
    if close > orb_h:
        direction = "BULLISH"
        action = "BUY_CE"
        score += 35
        reasons.append(f"ORB breakout above {orb_h:.0f}")

        # Volume confirmation
        vr = L.get("vol_ratio", 1)
        if vr >= cfg["min_volume_ratio"]:
            score += 20; reasons.append(f"Volume {vr:.1f}x confirms breakout")
        elif vr >= 1.5:
            score += 10

        # SuperTrend alignment
        if L.get("st_direction", 0) > 0:
            score += 15; reasons.append("SuperTrend bullish")

        # News alignment
        if news_score > 0.1:
            score += 10; reasons.append("News supports")

        sl = orb_l
        t1 = orb_h + orb_range * cfg["orb_target_mult"]
        t2 = orb_h + orb_range * 2.0

    # Breakout below ORB low
    elif close < orb_l:
        direction = "BEARISH"
        action = "BUY_PE"
        score += 35
        reasons.append(f"ORB breakdown below {orb_l:.0f}")

        vr = L.get("vol_ratio", 1)
        if vr >= cfg["min_volume_ratio"]:
            score += 20; reasons.append(f"Volume {vr:.1f}x confirms")
        elif vr >= 1.5:
            score += 10

        if L.get("st_direction", 0) < 0:
            score += 15; reasons.append("SuperTrend bearish")

        if news_score < -0.1:
            score += 10; reasons.append("News supports")

        sl = orb_h
        t1 = orb_l - orb_range * cfg["orb_target_mult"]
        t2 = orb_l - orb_range * 2.0

    else:
        empty.rejections.append("Price within ORB range — no breakout yet")
        return empty

    score = min(100, max(0, score))
    if score < cfg["min_confidence"]:
        action = "HOLD"

    rr = round(abs(t1 - close) / abs(close - sl), 2) if abs(close - sl) > 0 else 0
    sg = config.INSTRUMENTS.get(instrument, {}).get("strike_gap", 50)
    strike = round(close / sg) * sg
    ot = "CE" if direction == "BULLISH" else "PE"

    return Signal(action, direction, score, round(close, 2), round(sl, 2), round(t1, 2),
                  round(t2, 2), rr, instrument, "SCALPER", reasons, [], strike, ot)
