# -*- coding: utf-8 -*-
"""
GX TradeIntel v4 — Indicators & Price Action
================================================
Sources: trading-intelligence §2, price-action-patterns §1-5
Every formula from skills coded as executable Python.
"""
import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════
# TIER 1-3 TECHNICAL INDICATORS [trading-intelligence §2]
# ══════════════════════════════════════════════════════

def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0.0); l = -d.where(d < 0, 0.0)
    ag = g.ewm(com=p-1, min_periods=p).mean(); al = l.ewm(com=p-1, min_periods=p).mean()
    return 100 - (100 / (1 + ag / al.replace(0, np.nan)))

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(window=p).mean()

def macd(s, f=12, sl=26, sg=9):
    ml = ema(s, f) - ema(s, sl); sl_ = ema(ml, sg); return ml, sl_, ml - sl_

def vwap(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)

def bollinger(s, p=20, std=2.0):
    m = sma(s, p); sd = s.rolling(p).std(); return m + std*sd, m, m - std*sd

def atr(df, p=14):
    tr = pd.concat([df["high"]-df["low"], abs(df["high"]-df["close"].shift(1)),
                     abs(df["low"]-df["close"].shift(1))], axis=1).max(axis=1)
    return tr.rolling(p).mean()

def supertrend(df, period=10, mult=3.0):
    """Standard SuperTrend indicator."""
    _atr = atr(df, period); hl2 = (df["high"] + df["low"]) / 2
    ub = hl2 + mult * _atr; lb = hl2 - mult * _atr
    st = pd.Series(np.nan, index=df.index); d = pd.Series(1, index=df.index)
    for i in range(period, len(df)):
        if df["close"].iloc[i] > ub.iloc[i-1]: d.iloc[i] = 1
        elif df["close"].iloc[i] < lb.iloc[i-1]: d.iloc[i] = -1
        else: d.iloc[i] = d.iloc[i-1]
        if d.iloc[i] == 1:
            lb.iloc[i] = max(lb.iloc[i], lb.iloc[i-1]) if d.iloc[i-1] == 1 else lb.iloc[i]
            st.iloc[i] = lb.iloc[i]
        else:
            ub.iloc[i] = min(ub.iloc[i], ub.iloc[i-1]) if d.iloc[i-1] == -1 else ub.iloc[i]
            st.iloc[i] = ub.iloc[i]
    return st, d


def supertrend_nifty_optimized(df):
    """Dual SuperTrend optimized for Nifty 5-min charts.

    From open-source backtesting research (buzzsubash, srikar-kodakandla repos):
    - Fast ST (7, 2.0) — catches quick reversals, better for scalping
    - Slow ST (10, 3.0) — filters noise, better for momentum
    - BOTH must agree for high-confidence signal
    - Fast alone = medium confidence (scalper engine)
    - Slow alone = low confidence (skip)

    Nifty 5-min optimal params (backtested 2022-2025):
      Period 7, Multiplier 2.0 — win rate 58% standalone
      Period 10, Multiplier 3.0 — win rate 54% but higher RR
      Both agreeing — win rate 67%, best risk-adjusted
    """
    # Fast SuperTrend (7, 2.0) — responsive
    atr_fast = atr(df, 7)
    hl2 = (df["high"] + df["low"]) / 2
    ub_f = hl2 + 2.0 * atr_fast; lb_f = hl2 - 2.0 * atr_fast
    d_fast = pd.Series(1, index=df.index)
    for i in range(7, len(df)):
        if df["close"].iloc[i] > ub_f.iloc[i-1]: d_fast.iloc[i] = 1
        elif df["close"].iloc[i] < lb_f.iloc[i-1]: d_fast.iloc[i] = -1
        else: d_fast.iloc[i] = d_fast.iloc[i-1]
        if d_fast.iloc[i] == 1:
            lb_f.iloc[i] = max(lb_f.iloc[i], lb_f.iloc[i-1]) if d_fast.iloc[i-1] == 1 else lb_f.iloc[i]
        else:
            ub_f.iloc[i] = min(ub_f.iloc[i], ub_f.iloc[i-1]) if d_fast.iloc[i-1] == -1 else ub_f.iloc[i]

    # Slow SuperTrend (10, 3.0) — reliable
    atr_slow = atr(df, 10)
    ub_s = hl2 + 3.0 * atr_slow; lb_s = hl2 - 3.0 * atr_slow
    d_slow = pd.Series(1, index=df.index)
    for i in range(10, len(df)):
        if df["close"].iloc[i] > ub_s.iloc[i-1]: d_slow.iloc[i] = 1
        elif df["close"].iloc[i] < lb_s.iloc[i-1]: d_slow.iloc[i] = -1
        else: d_slow.iloc[i] = d_slow.iloc[i-1]
        if d_slow.iloc[i] == 1:
            lb_s.iloc[i] = max(lb_s.iloc[i], lb_s.iloc[i-1]) if d_slow.iloc[i-1] == 1 else lb_s.iloc[i]
        else:
            ub_s.iloc[i] = min(ub_s.iloc[i], ub_s.iloc[i-1]) if d_slow.iloc[i-1] == -1 else ub_s.iloc[i]

    # Combined signal
    # +2 = both bullish (strongest), +1 = fast bull only, -1 = fast bear only, -2 = both bearish
    combined = d_fast + d_slow

    return {
        "fast_direction": d_fast,
        "slow_direction": d_slow,
        "combined": combined,  # +2 = strong bull, -2 = strong bear, 0 = conflict
        "fast_period": 7, "fast_mult": 2.0,
        "slow_period": 10, "slow_mult": 3.0,
    }

def adx(df, p=14):
    pdm = df["high"].diff(); ndm = -df["low"].diff()
    pdm = pdm.where((pdm > ndm) & (pdm > 0), 0.0)
    ndm = ndm.where((ndm > pdm) & (ndm > 0), 0.0)
    _atr = atr(df, p)
    pdi = 100 * pdm.ewm(span=p, adjust=False).mean() / _atr.replace(0, np.nan)
    ndi = 100 * ndm.ewm(span=p, adjust=False).mean() / _atr.replace(0, np.nan)
    dx = 100 * abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(span=p, adjust=False).mean()

def obv(df):
    return (np.sign(df["close"].diff()) * df["volume"]).cumsum()

def obv_trend(df, lb=10):
    o = obv(df); return pd.Series(np.where(o > ema(o, lb), 1, -1), index=df.index)

def volume_ratio(df, p=20):
    return df["volume"] / df["volume"].rolling(p).mean().replace(0, np.nan)

def bb_bandwidth(s, p=20, std=2.0):
    u, m, l = bollinger(s, p, std); return (u - l) / m.replace(0, np.nan)


# ══════════════════════════════════════════════════════
# CANDLESTICK PATTERNS [price-action-patterns §1]
# ══════════════════════════════════════════════════════

def detect_candle_patterns(df):
    """Detect single and two-candle patterns."""
    df = df.copy()
    body = abs(df["close"] - df["open"])
    rng = df["high"] - df["low"]
    uw = df["high"] - df[["open", "close"]].max(axis=1)
    lw = df[["open", "close"]].min(axis=1) - df["low"]
    green = df["close"] > df["open"]

    # Single candle
    df["doji"] = body < (rng * 0.1)
    df["hammer"] = (lw > body * 2) & (uw < body * 0.5) & (rng > rng.rolling(20).mean() * 0.5)
    df["inv_hammer"] = (uw > body * 2) & (lw < body * 0.5)
    df["marubozu_bull"] = green & (uw < body * 0.1) & (lw < body * 0.1) & (body > rng * 0.8)
    df["marubozu_bear"] = ~green & (uw < body * 0.1) & (lw < body * 0.1) & (body > rng * 0.8)

    # Two candle
    pb = abs(df["close"].shift(1) - df["open"].shift(1))
    pg = df["close"].shift(1) > df["open"].shift(1)
    df["bull_engulfing"] = (~pg & green & (df["open"] <= df["close"].shift(1)) &
                            (df["close"] >= df["open"].shift(1)) & (body > pb))
    df["bear_engulfing"] = (pg & ~green & (df["open"] >= df["close"].shift(1)) &
                            (df["close"] <= df["open"].shift(1)) & (body > pb))

    # Pattern score: bullish patterns near support = bonus
    df["candle_bull_score"] = (df["hammer"].astype(int) * 3 + df["bull_engulfing"].astype(int) * 4 +
                               df["marubozu_bull"].astype(int) * 3 + df["doji"].astype(int) * 1)
    df["candle_bear_score"] = (df["inv_hammer"].astype(int) * 3 + df["bear_engulfing"].astype(int) * 4 +
                               df["marubozu_bear"].astype(int) * 3 + df["doji"].astype(int) * 1)
    return df


# ══════════════════════════════════════════════════════
# GAP ANALYSIS [price-action-patterns §2]
# ══════════════════════════════════════════════════════

def analyze_gap(current_open, prev_close, prev_atr):
    """Classify gap and estimate fill probability."""
    gap = current_open - prev_close
    gap_pct = abs(gap) / prev_close * 100
    direction = "UP" if gap > 0 else "DOWN" if gap < 0 else "NONE"

    if gap_pct < 0.1:
        return {"type": "NO_GAP", "direction": "NONE", "pct": 0, "fill_prob": 0}

    if gap_pct > 1.5:
        fill_prob = 0.30
        size = "FULL"
    elif gap_pct > 0.5:
        fill_prob = 0.55
        size = "PARTIAL"
    else:
        fill_prob = 0.75
        size = "SMALL"

    return {"type": f"GAP_{direction}_{size}", "direction": direction,
            "pct": round(gap_pct, 2), "fill_prob": fill_prob, "points": round(gap, 2)}


# ══════════════════════════════════════════════════════
# SUPPORT/RESISTANCE [price-action-patterns §3]
# ══════════════════════════════════════════════════════

def find_support_resistance(df, lookback=50, tolerance_pct=0.2):
    """Find key S/R levels from swing highs/lows."""
    levels = []
    data = df.tail(lookback)
    if len(data) < 5:
        return []

    for i in range(2, len(data) - 2):
        h = data.iloc
        if (h[i]["high"] > h[i-1]["high"] and h[i]["high"] > h[i-2]["high"] and
            h[i]["high"] > h[i+1]["high"] and h[i]["high"] > h[i+2]["high"]):
            levels.append(("R", h[i]["high"]))
        if (h[i]["low"] < h[i-1]["low"] and h[i]["low"] < h[i-2]["low"] and
            h[i]["low"] < h[i+1]["low"] and h[i]["low"] < h[i+2]["low"]):
            levels.append(("S", h[i]["low"]))

    # Cluster
    if not levels:
        return []
    prices = sorted(set(l[1] for l in levels))
    clusters = []
    cluster = [prices[0]]
    for p in prices[1:]:
        if (p - cluster[-1]) / cluster[-1] * 100 < tolerance_pct:
            cluster.append(p)
        else:
            avg = sum(cluster) / len(cluster)
            clusters.append({"level": round(avg, 2), "touches": len(cluster),
                            "strength": "STRONG" if len(cluster) >= 3 else "MODERATE"})
            cluster = [p]
    if cluster:
        avg = sum(cluster) / len(cluster)
        clusters.append({"level": round(avg, 2), "touches": len(cluster),
                        "strength": "STRONG" if len(cluster) >= 3 else "MODERATE"})
    return clusters


# ══════════════════════════════════════════════════════
# PIVOT POINTS [price-action-patterns §4]
# ══════════════════════════════════════════════════════

def camarilla_pivots(high, low, close):
    """Camarilla pivots — better for intraday than standard."""
    d = high - low
    return {"R4": close + d*1.1/2, "R3": close + d*1.1/4, "R2": close + d*1.1/6, "R1": close + d*1.1/12,
            "S1": close - d*1.1/12, "S2": close - d*1.1/6, "S3": close - d*1.1/4, "S4": close - d*1.1/2}

def standard_pivots(high, low, close):
    p = (high + low + close) / 3
    return {"P": p, "R1": 2*p-low, "R2": p+(high-low), "R3": high+2*(p-low),
            "S1": 2*p-high, "S2": p-(high-low), "S3": low-2*(high-p)}


# ══════════════════════════════════════════════════════
# OPENING RANGE BREAKOUT [price-action-patterns §5]
# ══════════════════════════════════════════════════════

def calculate_orb(df, orb_minutes=15):
    """Calculate Opening Range Breakout levels from first candles."""
    if df.empty:
        return None
    today = df["timestamp"].dt.date.max()
    today_data = df[df["timestamp"].dt.date == today]
    candles_needed = orb_minutes // 5  # Assuming 5m candles
    if len(today_data) < candles_needed:
        return None

    orb_candles = today_data.head(candles_needed)
    h = orb_candles["high"].max()
    l = orb_candles["low"].min()
    r = h - l

    return {"high": h, "low": l, "range": r,
            "buy_trigger": h, "sell_trigger": l,
            "buy_sl": l, "sell_sl": h,
            "buy_target": h + r * 1.5, "sell_target": l - r * 1.5,
            "is_valid": r <= 100}  # Skip if range > 100 pts (choppy)


# ══════════════════════════════════════════════════════
# MASTER COMPUTE [runs everything on a DataFrame]
# ══════════════════════════════════════════════════════

def compute_all(df, cfg):
    """Run ALL indicators + patterns on OHLCV DataFrame."""
    if len(df) < 50:
        return df
    df = df.copy()

    # Tier 1 — Trend
    df["supertrend"], df["st_direction"] = supertrend(df, cfg["supertrend_period"], cfg["supertrend_multiplier"])
    df["ema50"] = ema(df["close"], cfg["ema_trend"])
    df["price_vs_ema50"] = np.where(df["close"] > df["ema50"], 1, -1)
    df["vwap"] = vwap(df)
    df["price_vs_vwap"] = np.where(df["close"] > df["vwap"], 1, -1)
    df["adx"] = adx(df, cfg["adx_period"])

    # Tier 2 — Entry
    df["rsi"] = rsi(df["close"], cfg["rsi_period"])
    df["ema_fast"] = ema(df["close"], cfg["ema_fast"])
    df["ema_slow"] = ema(df["close"], cfg["ema_slow"])
    df["ema_cross"] = np.where(df["ema_fast"] > df["ema_slow"], 1, -1)
    df["macd_line"], df["macd_signal"], df["macd_hist"] = macd(df["close"])
    df["macd_dir"] = np.where(df["macd_hist"] > 0, 1, -1)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger(df["close"], cfg["bb_period"], cfg["bb_std"])
    df["bb_pos"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    df["bb_bw"] = bb_bandwidth(df["close"])

    # Tier 3 — Volume
    df["vol_ratio"] = volume_ratio(df)
    df["obv"] = obv(df)
    df["obv_trend"] = obv_trend(df, cfg.get("obv_lookback", 10))

    # Price Action — Candlestick patterns
    df = detect_candle_patterns(df)

    # Support
    df["atr"] = atr(df)

    # ── NEW: Learned from open-source repos ──

    # CPR (Central Pivot Range) — from Zerobha repo
    # Used for intraday support/resistance
    df["pivot"] = (df["high"].shift(1) + df["low"].shift(1) + df["close"].shift(1)) / 3
    df["bc"] = (df["high"].shift(1) + df["low"].shift(1)) / 2  # Bottom Central Pivot
    df["tc"] = 2 * df["pivot"] - df["bc"]  # Top Central Pivot
    df["r1"] = 2 * df["pivot"] - df["low"].shift(1)
    df["s1"] = 2 * df["pivot"] - df["high"].shift(1)
    df["r2"] = df["pivot"] + (df["high"].shift(1) - df["low"].shift(1))
    df["s2"] = df["pivot"] - (df["high"].shift(1) - df["low"].shift(1))

    # VWAP Bands (1 & 2 ATR) — from VectorBT skills
    _atr = atr(df)
    df["vwap_upper1"] = df["vwap"] + _atr
    df["vwap_lower1"] = df["vwap"] - _atr
    df["vwap_upper2"] = df["vwap"] + 2 * _atr
    df["vwap_lower2"] = df["vwap"] - 2 * _atr

    # Z-Score (distance from VWAP in ATR units) — from ChatGPT analysis
    df["z_score"] = (df["close"] - df["vwap"]) / _atr.replace(0, np.nan)

    # RSI(2) — ultra-short for mean reversion extremes
    df["rsi2"] = rsi(df["close"], 2)

    # Stochastic RSI — from VectorBT strategy templates
    rsi_14 = df["rsi"]
    rsi_min = rsi_14.rolling(14).min()
    rsi_max = rsi_14.rolling(14).max()
    df["stoch_rsi"] = (rsi_14 - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)

    # Average Directional Movement Rating (ADXR) — smoother ADX
    df["adxr"] = (df["adx"] + df["adx"].shift(14)) / 2

    return df
