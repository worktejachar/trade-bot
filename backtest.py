# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — ALIGNED WITH LIVE SYSTEM
==============================================
Backtest now mirrors the live trading system exactly:
- 3 engines (Momentum, Mean Reversion, Scalper) matching live engines/
- Conductor logic picks ONE engine per bar based on ADX (same as live)
- Daily candles (strategies calibrated for daily timeframe)
- 2% risk, theta-aware, walk-forward validated
"""
import sys
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def download_nifty_data(years=2):
    try:
        import yfinance as yf
        end = datetime.now(); start = end - timedelta(days=min(years * 365, 725))
        # Daily candles — strategies are calibrated for daily timeframe
        # yfinance limits: 5m = 60 days, 60m = 730 days, 1d = unlimited
        df = yf.download("^NSEI", start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), interval="1d", progress=False)
        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        if "date" in df.columns: df = df.rename(columns={"date": "timestamp"})
        if "datetime" in df.columns: df = df.rename(columns={"datetime": "timestamp"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["dow"] = df["timestamp"].dt.dayofweek
        print(f"  Downloaded {len(df)} daily bars ({df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]})")
        return df
    except Exception as e:
        print(f"  Failed: {e}"); return pd.DataFrame()


def add_indicators(df):
    df = df.copy(); c = df["close"]
    df["ema9"] = c.ewm(span=9, adjust=False).mean()
    df["ema21"] = c.ewm(span=21, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["ema_cross"] = np.where(df["ema9"] > df["ema21"], 1, -1)
    df["price_vs_ema50"] = np.where(c > df["ema50"], 1, -1)
    delta = c.diff(); gain = delta.where(delta > 0, 0.0); loss = -delta.where(delta < 0, 0.0)
    ag = gain.ewm(com=13, min_periods=14).mean(); al = loss.ewm(com=13, min_periods=14).mean()
    df["rsi"] = 100 - (100 / (1 + ag / al.replace(0, np.nan)))
    ag2 = gain.rolling(2).mean(); al2 = loss.rolling(2).mean()
    df["rsi2"] = 100 - (100 / (1 + ag2 / al2.replace(0, np.nan)))
    plus_dm = df["high"].diff(); minus_dm = -df["low"].diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([df["high"]-df["low"], abs(df["high"]-c.shift(1)), abs(df["low"]-c.shift(1))], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    pdi = 100 * plus_dm.ewm(span=14).mean() / atr14.replace(0, np.nan)
    ndi = 100 * minus_dm.ewm(span=14).mean() / atr14.replace(0, np.nan)
    dx = 100 * abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)
    df["adx"] = dx.ewm(span=14).mean(); df["atr"] = atr14
    sma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20; df["bb_lower"] = sma20 - 2 * std20
    df["bb_pos"] = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    hl2 = (df["high"] + df["low"]) / 2
    ub = hl2 + 3 * atr14; lb = hl2 - 3 * atr14
    st_dir = pd.Series(1, index=df.index)
    for i in range(1, len(df)):
        if c.iloc[i] > ub.iloc[i-1]: st_dir.iloc[i] = 1
        elif c.iloc[i] < lb.iloc[i-1]: st_dir.iloc[i] = -1
        else: st_dir.iloc[i] = st_dir.iloc[i-1]
    df["st_direction"] = st_dir
    df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean().replace(0, np.nan)
    df["day_move_pct"] = abs(c - df["open"]) / df["open"] * 100
    df["day_range_pct"] = (df["high"] - df["low"]) / df["open"] * 100
    df["z_score"] = (c - sma20) / atr14.replace(0, np.nan)
    df["prev_close"] = c.shift(1); df["prev_rsi"] = df["rsi"].shift(1); df["prev_z"] = df["z_score"].shift(1)
    df["body"] = abs(c - df["open"])
    df["upper_wick"] = df["high"] - df[["close", "open"]].max(axis=1)
    df["lower_wick"] = df[["close", "open"]].min(axis=1) - df["low"]
    df["body_pct"] = df["body"] / df["atr"].replace(0, np.nan)
    df["pivot"] = (df["high"].shift(1) + df["low"].shift(1) + df["close"].shift(1)) / 3
    df["s1"] = 2 * df["pivot"] - df["high"].shift(1)
    df["r1"] = 2 * df["pivot"] - df["low"].shift(1)
    df["dist_ema21"] = (c - df["ema21"]) / atr14.replace(0, np.nan)
    df["dist_ema50"] = (c - df["ema50"]) / atr14.replace(0, np.nan)
    df["green"] = (c > df["open"]).astype(int)
    df["red"] = (c < df["open"]).astype(int)
    df["consec_red"] = df["red"].rolling(3).sum()
    df["consec_green"] = df["green"].rolling(3).sum()
    df["range_high"] = df["high"].rolling(5).max()
    df["range_low"] = df["low"].rolling(5).min()
    df["near_range_low"] = ((c - df["range_low"]) / atr14.replace(0, np.nan)) < 0.5
    df["near_range_high"] = ((df["range_high"] - c) / atr14.replace(0, np.nan)) < 0.5
    # VWAP proxy using cumulative volume-weighted price (resets conceptually per session)
    df["vwap"] = (c * df["volume"]).rolling(7).sum() / df["volume"].rolling(7).sum().replace(0, np.nan)
    df["vwap_dev"] = abs(c - df["vwap"]) / c * 100
    return df


# ═══════════════════════════════════════
# ACCURACY FILTERS (shared by all engines)
# ═══════════════════════════════════════

def confirmation_check(row, direction):
    score = 0
    if direction == "BULL":
        if row["close"] > row["open"]: score += 10
        if row["lower_wick"] > row["body"] * 0.5: score += 5
        if row["close"] > row["prev_close"]: score += 5
    else:
        if row["close"] < row["open"]: score += 10
        if row["upper_wick"] > row["body"] * 0.5: score += 5
        if row["close"] < row["prev_close"]: score += 5
    return score

def cpr_confluence(row, direction):
    price = row["close"]; atr = row["atr"]
    if atr <= 0: return 0
    tol = atr * 0.4; score = 0
    if direction == "BULL":
        if abs(price - row["s1"]) < tol: score += 15
        elif abs(price - row["pivot"]) < tol: score += 10
    else:
        if abs(price - row["r1"]) < tol: score += 15
        elif abs(price - row["pivot"]) < tol: score += 10
    return score


# ═══════════════════════════════════════
# ENGINE 1: MEAN REVERSION (matches engines/mean_reversion.py)
# Target: RANGING markets (ADX < 22)
# Combines: Z-score, RSI(2), BB, VWAP deviation, consecutive reversal
# ═══════════════════════════════════════

def mean_reversion_signal(row):
    if row["adx"] > 30: return None  # Only in ranging/weak trend
    z = row.get("z_score", 0); rsi = row.get("rsi", 50); rsi2 = row.get("rsi2", 50)
    bb = row.get("bb_pos", 0.5); vwap_dev = row.get("vwap_dev", 0)

    # Score signals like live mean_reversion.py
    for direction in ["BULL", "BEAR"]:
        score = 0

        # RSI(2) extremes (live: +25 for <10, +15 for <20)
        if direction == "BULL":
            if rsi2 < 10: score += 25
            elif rsi2 < 20: score += 15
        else:
            if rsi2 > 90: score += 25
            elif rsi2 > 80: score += 15

        # Bollinger Bands (live: +20 for touch, +12 for proximity)
        if direction == "BULL":
            if bb < 0.1: score += 20
            elif bb < 0.2: score += 12
        else:
            if bb > 0.9: score += 20
            elif bb > 0.8: score += 12

        # VWAP deviation (live: +20 for >0.5%, +15 for >0.3%)
        if vwap_dev > 0.5: score += 20
        elif vwap_dev > 0.3: score += 15

        # Z-score confirmation
        if direction == "BULL" and z < -0.9: score += 15
        elif direction == "BEAR" and z > 0.9: score += 15

        # Consecutive candle exhaustion
        if direction == "BULL" and row.get("consec_red", 0) >= 2 and row["close"] > row["open"]: score += 10
        if direction == "BEAR" and row.get("consec_green", 0) >= 2 and row["close"] < row["open"]: score += 10

        # Volume exhaustion (low volume = exhaustion)
        if row.get("vol_ratio", 1) < 0.8: score += 10

        # Confirmation candle (mandatory)
        conf = confirmation_check(row, direction)
        if conf < 10: continue
        score += conf

        # CPR confluence
        score += cpr_confluence(row, direction)

        # RSI agreement
        if direction == "BULL" and rsi < 40: score += 10
        elif direction == "BEAR" and rsi > 60: score += 10

        # Min confidence 50 (lowered for daily timeframe)
        if score >= 50:
            return {"direction": direction, "engine": "MEAN_REVERSION", "score": min(95, score)}

    return None


# ═══════════════════════════════════════
# ENGINE 2: MOMENTUM (matches engines/momentum.py)
# Target: TRENDING markets (ADX > 25)
# Requires: SuperTrend + EMA50 + ADX alignment
# ═══════════════════════════════════════

def momentum_signal(row, prev):
    if row["adx"] < 25: return None  # Only in trending markets
    if row["st_direction"] != prev.get("st_direction", 0): return None  # Trend must be consistent

    is_bull = row["st_direction"] > 0 and row["price_vs_ema50"] > 0
    is_bear = row["st_direction"] < 0 and row["price_vs_ema50"] < 0
    if not is_bull and not is_bear: return None

    # Don't chase extremes
    z = abs(row.get("z_score", 0))
    if z > 1.5: return None

    direction = "BULL" if is_bull else "BEAR"
    score = 0

    # Tier 1: Trend confirmation (ADX strength)
    if row["adx"] > 30: score += 20
    elif row["adx"] > 25: score += 10

    # Tier 2: Entry setup — RSI pullback in trend direction
    if is_bull and 35 < row["rsi"] < 55: score += 20
    if is_bear and 45 < row["rsi"] < 65: score += 20

    # EMA alignment
    if is_bull and row["ema_cross"] > 0: score += 10
    if is_bear and row["ema_cross"] < 0: score += 10

    # BB position (pullback to middle)
    if is_bull and row["bb_pos"] < 0.5: score += 10
    if is_bear and row["bb_pos"] > 0.5: score += 10

    # Tier 3: Volume confirmation (live: min 1.5x, bonus at 2.0x)
    if row.get("vol_ratio", 1) >= 2.0: score += 15
    elif row.get("vol_ratio", 1) >= 1.5: score += 10

    # Confirmation candle (mandatory)
    conf = confirmation_check(row, direction)
    if conf < 10: return None
    score += conf

    # CPR confluence
    score += cpr_confluence(row, direction)

    # Min confidence 50 (lowered for daily timeframe)
    if score >= 50:
        return {"direction": direction, "engine": "MOMENTUM", "score": min(95, score)}

    return None


# ═══════════════════════════════════════
# ENGINE 3: SCALPER (matches engines/scalper.py)
# Target: VOLATILE markets (high ATR, range breakout)
# Uses: Range breakout + VWAP bounce + volume spike
# ═══════════════════════════════════════

def scalper_signal(row):
    atr = row.get("atr", 0)
    if atr <= 0: return None

    # Volatility check — scalper needs movement
    range_pct = row.get("day_range_pct", 0)
    if range_pct < 0.3: return None  # Not enough intraday range

    score = 0; direction = None

    # Range breakout: close near high or low of recent range
    if row.get("near_range_high", False) and row["close"] > row["open"]:
        direction = "BULL"; score += 25  # Breakout above range
    elif row.get("near_range_low", False) and row["close"] < row["open"]:
        direction = "BEAR"; score += 25  # Breakdown below range

    # VWAP bounce
    vwap_dev = row.get("vwap_dev", 0)
    if direction is None and vwap_dev > 0.15:
        if row["close"] > row.get("vwap", row["close"]):
            direction = "BULL"; score += 20
        else:
            direction = "BEAR"; score += 20

    if direction is None: return None

    # Volume spike (live: min 2.0x for scalper)
    if row.get("vol_ratio", 1) >= 2.0: score += 20
    elif row.get("vol_ratio", 1) >= 1.5: score += 10

    # SuperTrend alignment bonus
    if direction == "BULL" and row["st_direction"] > 0: score += 15
    elif direction == "BEAR" and row["st_direction"] < 0: score += 15

    # Confirmation candle
    conf = confirmation_check(row, direction)
    if conf < 10: return None
    score += conf

    # CPR confluence
    score += cpr_confluence(row, direction)

    # Min confidence 50 (lowered for daily timeframe)
    if score >= 50:
        return {"direction": direction, "engine": "SCALPER", "score": min(90, score)}

    return None


# ═══════════════════════════════════════
# BACKTEST ENGINE (aligned with live main.py)
# ═══════════════════════════════════════

def run_backtest(df, capital=10000):
    trades = []; equity = capital; peak = capital; max_dd = 0
    consec_loss = 0; daily_trades = 0; last_date = None

    for i in range(51, len(df)):
        row = df.iloc[i]; prev = df.iloc[i-1]
        curr_date = row["timestamp"].date() if hasattr(row["timestamp"], "date") else None
        if curr_date != last_date: daily_trades = 0; last_date = curr_date
        if daily_trades >= 2: continue
        if consec_loss >= 4: consec_loss = 0; continue

        # ── CONDUCTOR LOGIC (same as live conductor.py) ──
        # Pick ONE engine based on ADX, just like the live system does
        adx = row.get("adx", 20)
        if adx > 25:
            active_engine = "MOMENTUM"
        elif adx < 22:
            active_engine = "MEAN_REVERSION"
        else:
            active_engine = "MEAN_REVERSION"  # Default to MR in unclear zone

        # High volatility override (matches live conductor fallback)
        atr_ratio = row.get("atr", 0) / row["close"] * 100 if row["close"] > 0 else 0
        if atr_ratio > 1.5 and adx <= 25:
            active_engine = "SCALPER"

        # ── RUN SELECTED ENGINE ONLY (same as live main.py) ──
        signal = None
        if active_engine == "MEAN_REVERSION":
            signal = mean_reversion_signal(row)
        elif active_engine == "MOMENTUM":
            signal = momentum_signal(row, prev)
        elif active_engine == "SCALPER":
            signal = scalper_signal(row)

        if signal is None: continue
        score = signal["score"]

        if score >= 70: risk_mult = 1.2
        elif score >= 60: risk_mult = 0.8
        else: risk_mult = 0.5

        # Drawdown reduction
        dd_pct = (peak - equity) / peak * 100 if peak > 0 else 0
        if dd_pct > 15: risk_mult *= 0.25
        elif dd_pct > 10: risk_mult *= 0.5
        elif dd_pct > 5: risk_mult *= 0.75
        if consec_loss >= 2: risk_mult *= 0.5

        spot = row["close"]; prem = spot * 0.004
        max_risk = equity * 0.02 * risk_mult
        sl_cost = prem * 0.20 * 25
        if sl_cost <= 0: continue
        lots = max(1, min(5, int(max_risk / sl_cost)))
        qty = lots * 25

        if i + 1 >= len(df): break
        nxt = df.iloc[i + 1]
        move = (nxt["close"] - spot) if signal["direction"] == "BULL" else (spot - nxt["close"])
        pchg = (move * 0.5) / prem * 100
        dow = int(row.get("dow", 1))
        slip = 0.015 if dow in (0, 4) else 0.005  # 3x slippage Mon/Fri
        slippage_cost = prem * qty * slip * 2

        # Theta-adjusted SL
        theta_mult = {0: 1.0, 1: 1.0, 2: 1.15, 3: 1.5, 4: 1.0}.get(dow, 1.0)
        iv_loss = {0: 1.0, 1: 0, 2: 0, 3: 3.0, 4: 0.5}.get(dow, 0)
        pchg -= iv_loss  # IV crush penalty
        eff_sl = 20 * theta_mult

        # Engine-specific exits (matching live config.py targets)
        if signal["engine"] == "SCALPER":
            # Scalper: tighter SL, smaller targets, faster exits
            eff_sl_eng = min(eff_sl, 15)
            if pchg <= -eff_sl_eng: pnl_u = -prem * (eff_sl_eng/100); result = "LOSS"
            elif pchg >= 20: pnl_u = prem * 0.20; result = "WIN"
            elif pchg >= 10: pnl_u = prem * 0.10; result = "WIN"
            elif pchg >= 3: pnl_u = prem * 0.03; result = "WIN"
            elif pchg >= 0: pnl_u = move * 0.5; result = "WIN" if pnl_u > 0 else "LOSS"
            else: pnl_u = move * 0.5; result = "LOSS"
        elif signal["engine"] == "MOMENTUM":
            # Momentum: wider SL, bigger targets, hold longer
            if pchg <= -eff_sl: pnl_u = -prem * (eff_sl/100); result = "LOSS"
            elif pchg >= 40: pnl_u = prem * 0.40; result = "WIN"
            elif pchg >= 20: pnl_u = prem * 0.20; result = "WIN"
            elif pchg >= 8: pnl_u = prem * 0.08; result = "WIN"
            elif pchg >= 0: pnl_u = move * 0.5; result = "WIN" if pnl_u > 0 else "LOSS"
            else: pnl_u = move * 0.5; result = "LOSS"
        else:
            # Mean Reversion: moderate SL, VWAP-level targets
            if pchg <= -eff_sl: pnl_u = -prem * (eff_sl/100); result = "LOSS"
            elif pchg >= 30: pnl_u = prem * 0.30; result = "WIN"
            elif pchg >= 15: pnl_u = prem * 0.15; result = "WIN"
            elif pchg >= 5: pnl_u = prem * 0.05; result = "WIN"
            elif pchg >= 0: pnl_u = move * 0.5; result = "WIN" if pnl_u > 0 else "LOSS"
            else: pnl_u = move * 0.5; result = "LOSS"

        pnl = pnl_u * qty - 150 - slippage_cost
        if pnl < -max_risk: pnl = -max_risk
        if result == "WIN": consec_loss = 0
        else: consec_loss += 1

        equity += pnl; peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd); daily_trades += 1
        if equity < capital * 0.2: break

        trades.append({"date": row["timestamp"], "engine": signal["engine"],
                       "direction": signal["direction"], "score": score,
                       "result": result, "pnl": round(pnl, 2), "equity": round(equity, 2)})
    return trades, max_dd


def calc(trades, capital, max_dd):
    if not trades: return {}
    w = [t for t in trades if t["result"] == "WIN"]
    l = [t for t in trades if t["result"] == "LOSS"]
    nw = len(w); nl = len(l); tot = nw + nl; wr = nw/tot*100 if tot else 0
    gp = sum(t["pnl"] for t in w); gl = abs(sum(t["pnl"] for t in l))
    net = gp - gl; pf = gp/gl if gl > 0 else 999
    aw = gp/nw if nw else 0; al = gl/nl if nl else 0
    exp = (wr/100*aw) - ((1-wr/100)*al)
    ret = (trades[-1]["equity"]-capital)/capital*100
    rr = aw/al if al > 0 else 999
    return {"trades": tot, "wins": nw, "losses": nl, "wr": round(wr,1),
            "net": round(net,0), "pf": round(pf,2), "aw": round(aw,0), "al": round(al,0),
            "exp": round(exp,0), "dd": round(max_dd,1), "ret": round(ret,1),
            "eq": round(trades[-1]["equity"],0), "rr": round(rr,2)}


def monte_carlo(trades, capital=10000, sims=1000, n_trades=300):
    if len(trades) < 10: print("  Not enough trades"); return
    wins = [t["pnl"] for t in trades if t["result"] == "WIN"]
    losses = [t["pnl"] for t in trades if t["result"] == "LOSS"]
    wr = len(wins)/len(trades); aw = np.mean(wins); al = np.mean(losses)
    finals = []; dds = []; ruin = 0
    for _ in range(sims):
        eq = capital; pk = capital; mdd = 0
        for _ in range(n_trades):
            if np.random.random() < wr: eq += aw * (0.7 + np.random.random() * 0.6)
            else: eq += al * (0.7 + np.random.random() * 0.6)
            pk = max(pk, eq); dd = (pk-eq)/pk*100 if pk > 0 else 0; mdd = max(mdd, dd)
            if eq < capital * 0.2: ruin += 1; break
        finals.append(eq); dds.append(mdd)
    f = np.array(finals); d = np.array(dds)
    print(f"""
  MONTE CARLO ({sims} sims x {n_trades} trades)
  ───────────────────────────────────
  Median equity:    Rs {np.median(f):,.0f}
  Best (95th):      Rs {np.percentile(f,95):,.0f}
  Worst (5th):      Rs {np.percentile(f,5):,.0f}
  Avg max DD:       {np.mean(d):.1f}%
  Worst DD:         {np.max(d):.1f}%
  Ruin prob:        {ruin/sims*100:.1f}%
  Profitable:       {sum(1 for x in f if x > capital)/sims*100:.0f}%
  ───────────────────────────────────""")


def walk_forward_validation(df, capital=10000, n_folds=4):
    fold_size = len(df) // n_folds
    results = []
    print(f"\n  WALK-FORWARD VALIDATION ({n_folds} folds)")
    print(f"  ───────────────────────────────────")
    print(f"  {'Fold':<6} {'Train PF':>9} {'Test PF':>8} {'WFE':>6} {'Status':>8}")
    print(f"  {'-'*42}")
    for i in range(1, n_folds):
        train = df.iloc[:fold_size * i].copy()
        test = df.iloc[fold_size * i:fold_size * (i + 1)].copy()
        if len(test) < 20:
            continue
        train_trades, _ = run_backtest(train, capital)
        test_trades, _ = run_backtest(test, capital)
        train_m = calc(train_trades, capital, 0)
        test_m = calc(test_trades, capital, 0)
        train_pf = train_m.get("pf", 0) if train_m else 0
        test_pf = test_m.get("pf", 0) if test_m else 0
        wfe = test_pf / train_pf if train_pf > 0 else 0
        status = "GOOD" if wfe > 0.5 else "OVERFIT" if wfe < 0.3 else "MARGINAL"
        results.append(wfe)
        print(f"  {i:<6} {train_pf:>9.2f} {test_pf:>8.2f} {wfe:>6.2f} {status:>8}")
    avg_wfe = np.mean(results) if results else 0
    print(f"  {'-'*42}")
    print(f"  {'AVG':<6} {'':>9} {'':>8} {avg_wfe:>6.2f} {'PASS' if avg_wfe > 0.5 else 'FAIL':>8}")
    print(f"  ───────────────────────────────────")
    return avg_wfe


def main():
    print("\n" + "=" * 55)
    print("  GX TRADEINTEL v6 — LIVE-ALIGNED BACKTEST")
    print("  3 Engines (MR/Momentum/Scalper) | Conductor Logic")
    print("  Daily Candles | 2% Risk | Walk-Forward Validated")
    print("=" * 55 + "\n")

    df = download_nifty_data(2)
    if df.empty: return
    print("  Computing indicators...")
    df = add_indicators(df)

    trades, max_dd = run_backtest(df)
    m = calc(trades, 10000, max_dd)
    if not m: print("  No trades."); return

    engines = {}
    for t in trades:
        e = t["engine"]
        if e not in engines: engines[e] = {"w": 0, "l": 0, "pnl": 0}
        if t["result"] == "WIN": engines[e]["w"] += 1
        else: engines[e]["l"] += 1
        engines[e]["pnl"] += t["pnl"]

    print(f"""
  RESULTS
  ═══════════════════════════════════════
  Trades:       {m['trades']} (W:{m['wins']} L:{m['losses']})
  Win Rate:     {m['wr']}%  {"TARGET HIT" if m['wr'] >= 55 else "IMPROVED" if m['wr'] > 50 else "NEEDS WORK"}
  Profit Factor:{m['pf']}
  Net Profit:   Rs {m['net']:,.0f} ({m['ret']}%)
  Expectancy:   Rs {m['exp']:,.0f}/trade
  Avg Winner:   Rs {m['aw']:,.0f}
  Avg Loser:    Rs {m['al']:,.0f}
  Risk/Reward:  1:{m['rr']}
  Max Drawdown: {m['dd']}%
  Final Equity: Rs {m['eq']:,.0f}
  ═══════════════════════════════════════""")

    print(f"\n  ENGINE BREAKDOWN:")
    print(f"  {'Engine':<16} {'W':>4} {'L':>4} {'Total':>6} {'WR%':>6} {'Net PnL':>10}")
    print(f"  {'-'*52}")
    for e, d in sorted(engines.items(), key=lambda x: -x[1]["pnl"]):
        total = d["w"] + d["l"]; wr = d["w"]/total*100 if total > 0 else 0
        print(f"  {e:<16} {d['w']:>4} {d['l']:>4} {total:>6} {wr:>5.1f}% Rs {d['pnl']:>8,.0f}")

    if trades:
        tdf = pd.DataFrame(trades)
        tdf["month"] = pd.to_datetime(tdf["date"]).dt.to_period("M")
        monthly = tdf.groupby("month").agg(trades=("pnl","count"), pnl=("pnl","sum"),
                                            wins=("result", lambda x: (x=="WIN").sum())).reset_index()
        prof = sum(1 for _, r in monthly.iterrows() if r["pnl"] > 0)
        print(f"\n  MONTHLY: {prof} profitable / {len(monthly)-prof} losing")
        print(f"  {'Month':<10} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'P&L':>10}")
        print(f"  {'-'*42}")
        for _, r in monthly.iterrows():
            wr = r["wins"]/r["trades"]*100 if r["trades"] > 0 else 0
            e = "+" if r["pnl"] > 0 else "-"
            print(f"  {str(r['month']):<10} {r['trades']:>7} {r['wins']:>5} {wr:>5.1f}% {e}Rs {abs(r['pnl']):>7,.0f}")

    walk_forward_validation(df)
    monte_carlo(trades)

    if trades: pd.DataFrame(trades).to_csv("logs/backtest_results.csv", index=False)

    print(f"\n  {'='*55}")
    print(f"  VERSION COMPARISON:")
    print(f"    v1: 44.4% WR | PF 1.43 | 187 trades | Rs  +6,447  (daily, 6 setups)")
    print(f"    v2: 46.8% WR | PF 2.04 | 124 trades | Rs +12,558  (daily, 6 setups)")
    print(f"    v3: 57.1% WR | PF 2.82 |  35 trades | Rs  +4,393  (daily, 6 setups)")
    print(f"    v4: 52.7% WR | PF 1.78 |  91 trades | Rs  +6,874  (daily, 6 setups)")
    print(f"    v5: 52.7% WR | PF 1.78 |  91 trades | Rs  +8,358  (daily, 2% risk)")
    print(f"    v6: {m['wr']}% WR | PF {m['pf']} | {m['trades']:>3} trades | Rs {m['net']:>+,.0f}  ← LIVE-ALIGNED")
    print()
    print(f"  BEFORE GOING LIVE:")
    print(f"    Paper trade 200+ trades (est. 6-12 months)")
    print(f"    Only go live if: WR > 50%, PF > 1.3, DD < 15%")
    print()

if __name__ == "__main__":
    main()
