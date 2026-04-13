# -*- coding: utf-8 -*-
"""
GX TradeIntel v5 — Regime Detector
=====================================
Source: market-regime-detection skill
Classifies market into TRENDING/RANGING/VOLATILE/UNCLEAR
"""
import numpy as np
import pandas as pd
import config


def detect_regime(df, vix=0):
    """Classify market regime from 15-minute OHLCV data with indicators."""
    if df is None or len(df) < 20:
        return {"regime": "UNCLEAR", "confidence": 0, "scores": {}, "direction": "NONE"}

    latest = df.iloc[-1]
    cfg = config.REGIME

    adx_val = latest.get("adx", 20)
    bb_bw = latest.get("bb_bw", 0)
    bb_bw_avg = df["bb_bw"].rolling(20).mean().iloc[-1] if "bb_bw" in df.columns else bb_bw
    bb_expanding = bb_bw > bb_bw_avg * cfg["bb_expansion_threshold"] if bb_bw_avg > 0 else False

    atr_cur = latest.get("atr", 0)
    atr_avg = df["atr"].rolling(20).mean().iloc[-1] if "atr" in df.columns else atr_cur
    atr_ratio = atr_cur / atr_avg if atr_avg > 0 else 1.0

    # Price structure
    lb = cfg["structure_lookback"]
    highs = df["high"].tail(lb)
    lows = df["low"].tail(lb)
    hh = sum(1 for i in range(1, len(highs)) if highs.iloc[i] > highs.iloc[i-1])
    ll = sum(1 for i in range(1, len(lows)) if lows.iloc[i] < lows.iloc[i-1])
    trending_struct = hh >= lb * 0.6 or ll >= lb * 0.6
    direction = "UP" if hh >= lb * 0.6 else "DOWN" if ll >= lb * 0.6 else "MIXED"

    # Candle color consistency
    greens = sum(1 for i in range(len(df)-lb, len(df)) if df["close"].iloc[i] > df["open"].iloc[i])
    color_consistent = greens >= lb * 0.7 or greens <= lb * 0.3

    # SCORING
    t, r, v = 0, 0, 0

    if adx_val > 30: t += 3
    elif adx_val > cfg["adx_trending"]: t += 2
    elif adx_val < 18: r += 3
    elif adx_val < cfg["adx_ranging"]: r += 2

    if bb_expanding: t += 2; v += 1
    else: r += 2

    if atr_ratio > cfg["atr_volatile_ratio"]: v += 3
    elif atr_ratio > 1.2: t += 1; v += 1
    elif atr_ratio < 0.8: r += 2

    if trending_struct: t += 2
    else: r += 1

    if color_consistent: t += 1
    else: r += 1

    if vix > 25: v += 2
    elif vix > 20: v += 1
    elif vix < 14: r += 1

    scores = {"TRENDING": t, "RANGING": r, "VOLATILE": v}
    top = max(scores, key=scores.get)
    top_score = scores[top]
    second = sorted(scores.values(), reverse=True)[1]

    if top_score - second <= 1:
        regime = "UNCLEAR"
        conf = 30
    else:
        regime = top
        conf = min(95, 50 + (top_score - second) * 10)

    return {
        "regime": regime,
        "confidence": conf,
        "scores": scores,
        "adx": round(adx_val, 1),
        "atr_ratio": round(atr_ratio, 2),
        "bb_expanding": bb_expanding,
        "structure": direction,
        "direction": direction if regime == "TRENDING" else "NONE",
    }
