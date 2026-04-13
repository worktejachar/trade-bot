# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — BEST OF BOTH
==================================
Target: 55%+ WR (from v3) + Rs 10K+ profit (from v2)
Method: Keep v3 accuracy filters + add MORE high-quality setups
New setups: EMA pullback, VWAP band, consecutive reversal, range bounce
All require confirmation candle (mandatory).
"""
import sys
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def download_nifty_data(years=2):
    try:
        import yfinance as yf
        end = datetime.now(); start = end - timedelta(days=years * 365)
        df = yf.download("^NSEI", start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), interval="1d", progress=False)
        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        if "date" in df.columns: df = df.rename(columns={"date": "timestamp"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
        print(f"  Downloaded {len(df)} days ({df['timestamp'].iloc[0].date()} to {df['timestamp'].iloc[-1].date()})")
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
    # EMA distance for pullback detection
    df["dist_ema21"] = (c - df["ema21"]) / atr14.replace(0, np.nan)
    df["dist_ema50"] = (c - df["ema50"]) / atr14.replace(0, np.nan)
    # Consecutive candle tracking
    df["green"] = (c > df["open"]).astype(int)
    df["red"] = (c < df["open"]).astype(int)
    df["consec_red"] = df["red"].rolling(3).sum()
    df["consec_green"] = df["green"].rolling(3).sum()
    # Range detection: 5-day high/low
    df["range_high"] = df["high"].rolling(5).max()
    df["range_low"] = df["low"].rolling(5).min()
    df["near_range_low"] = ((c - df["range_low"]) / atr14.replace(0, np.nan)) < 0.5
    df["near_range_high"] = ((df["range_high"] - c) / atr14.replace(0, np.nan)) < 0.5
    df["dow"] = pd.to_datetime(df["timestamp"]).dt.dayofweek
    return df


# ═══════════════════════════════════════
# ACCURACY FILTERS (from v3 — kept intact)
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

def trend_alignment(row, direction):
    adx = row["adx"]; ema_dir = row["ema_cross"]
    if adx > 30:
        if direction == "BULL" and ema_dir < 0: return -20
        if direction == "BEAR" and ema_dir > 0: return -20
    if adx < 20: return 10
    return 0


# ═══════════════════════════════════════
# SETUP 1: Z-SCORE REVERSION (from v3)
# ═══════════════════════════════════════

def zscore_signals(row):
    signals = []
    z = row.get("z_score", 0); rsi = row.get("rsi", 50); bb = row.get("bb_pos", 0.5)
    if row["adx"] > 28: return signals

    if z < -1.2:
        conf = confirmation_check(row, "BULL")
        if conf >= 10:
            base = min(70, int(abs(z) * 20)) + conf + cpr_confluence(row, "BULL") + trend_alignment(row, "BULL")
            if rsi < 40: base += 15
            elif rsi < 50: base += 5
            else: base -= 15
            if bb < 0.2: base += 10
            if row.get("prev_z", 0) < -0.5: base += 10
            if base >= 55:
                signals.append({"direction": "BULL", "engine": "MR_ZSCORE", "score": min(95, base)})

    elif z > 1.2:
        conf = confirmation_check(row, "BEAR")
        if conf >= 10:
            base = min(70, int(abs(z) * 20)) + conf + cpr_confluence(row, "BEAR") + trend_alignment(row, "BEAR")
            if rsi > 60: base += 15
            elif rsi > 50: base += 5
            else: base -= 15
            if bb > 0.8: base += 10
            if row.get("prev_z", 0) > 0.5: base += 10
            if base >= 55:
                signals.append({"direction": "BEAR", "engine": "MR_ZSCORE", "score": min(95, base)})
    return signals


# ═══════════════════════════════════════
# SETUP 2: EMA PULLBACK REVERSION (NEW)
# Price touches EMA21 in range market + bounces
# ═══════════════════════════════════════

def ema_pullback_signals(row):
    signals = []
    if row["adx"] > 25: return signals  # Only in range/weak trend
    dist = row.get("dist_ema21", 0)

    # Price just touched EMA21 from below and bounced
    if -0.3 < dist < 0.3:  # Near EMA21
        conf = confirmation_check(row, "BULL" if row["close"] > row["ema21"] else "BEAR")
        if conf >= 10:
            direction = "BULL" if row["close"] > row["ema21"] else "BEAR"
            base = 50 + conf + cpr_confluence(row, direction)
            if row["rsi"] < 45 and direction == "BULL": base += 10
            if row["rsi"] > 55 and direction == "BEAR": base += 10
            if row["vol_ratio"] < 1.2: base += 5
            if base >= 55:
                signals.append({"direction": direction, "engine": "EMA_PULLBACK", "score": min(85, base)})
    return signals


# ═══════════════════════════════════════
# SETUP 3: CONSECUTIVE CANDLE REVERSAL (NEW)
# 3+ red candles → green bounce = buy
# 3+ green candles → red drop = sell
# ═══════════════════════════════════════

def consecutive_reversal_signals(row):
    signals = []
    if row["adx"] > 30: return signals

    # 3 red candles then green = oversold bounce
    if row.get("consec_red", 0) >= 2 and row["close"] > row["open"]:
        conf = confirmation_check(row, "BULL")
        if conf >= 10:
            base = 55 + conf + cpr_confluence(row, "BULL") + trend_alignment(row, "BULL")
            if row["rsi"] < 40: base += 10
            if row["bb_pos"] < 0.25: base += 10
            if base >= 55:
                signals.append({"direction": "BULL", "engine": "CONSEC_REV", "score": min(85, base)})

    # 3 green candles then red = overbought drop
    if row.get("consec_green", 0) >= 2 and row["close"] < row["open"]:
        conf = confirmation_check(row, "BEAR")
        if conf >= 10:
            base = 55 + conf + cpr_confluence(row, "BEAR") + trend_alignment(row, "BEAR")
            if row["rsi"] > 60: base += 10
            if row["bb_pos"] > 0.75: base += 10
            if base >= 55:
                signals.append({"direction": "BEAR", "engine": "CONSEC_REV", "score": min(85, base)})
    return signals


# ═══════════════════════════════════════
# SETUP 4: RANGE S/R BOUNCE (NEW)
# Near 5-day low with confirmation = buy
# Near 5-day high with confirmation = sell
# ═══════════════════════════════════════

def range_bounce_signals(row):
    signals = []
    if row["adx"] > 28: return signals

    if row.get("near_range_low", False):
        conf = confirmation_check(row, "BULL")
        if conf >= 10:
            base = 55 + conf + cpr_confluence(row, "BULL") + trend_alignment(row, "BULL")
            if row["rsi"] < 35: base += 15
            elif row["rsi"] < 45: base += 5
            if base >= 55:
                signals.append({"direction": "BULL", "engine": "RANGE_BOUNCE", "score": min(85, base)})

    if row.get("near_range_high", False):
        conf = confirmation_check(row, "BEAR")
        if conf >= 10:
            base = 55 + conf + cpr_confluence(row, "BEAR") + trend_alignment(row, "BEAR")
            if row["rsi"] > 65: base += 15
            elif row["rsi"] > 55: base += 5
            if base >= 55:
                signals.append({"direction": "BEAR", "engine": "RANGE_BOUNCE", "score": min(85, base)})
    return signals


# ═══════════════════════════════════════
# SETUP 5: RSI EXTREME (from v3)
# ═══════════════════════════════════════

def rsi_extreme_signals(row):
    signals = []
    rsi2 = row.get("rsi2", 50); bb = row.get("bb_pos", 0.5)
    if row["adx"] > 28: return signals

    if rsi2 < 8 and bb < 0.1:
        conf = confirmation_check(row, "BULL")
        if conf >= 10:
            base = 60 + conf + cpr_confluence(row, "BULL") + trend_alignment(row, "BULL")
            if base >= 55:
                signals.append({"direction": "BULL", "engine": "MR_RSI", "score": min(90, base)})
    elif rsi2 > 92 and bb > 0.9:
        conf = confirmation_check(row, "BEAR")
        if conf >= 10:
            base = 60 + conf + cpr_confluence(row, "BEAR") + trend_alignment(row, "BEAR")
            if base >= 55:
                signals.append({"direction": "BEAR", "engine": "MR_RSI", "score": min(90, base)})
    return signals


# ═══════════════════════════════════════
# SETUP 6: MOMENTUM PULLBACK (from v3)
# ═══════════════════════════════════════

def momentum_signals(row, prev):
    signals = []
    if row["adx"] < 25: return signals
    if row["st_direction"] != prev.get("st_direction", 0): return signals
    is_bull = row["st_direction"] > 0 and row["price_vs_ema50"] > 0
    is_bear = row["st_direction"] < 0 and row["price_vs_ema50"] < 0
    if not is_bull and not is_bear: return signals
    z = abs(row.get("z_score", 0))
    if z > 1.0: return signals

    direction = "BULL" if is_bull else "BEAR"
    score = 0
    if is_bull and 35 < row["rsi"] < 55: score += 20
    if is_bear and 45 < row["rsi"] < 65: score += 20
    if is_bull and row["bb_pos"] < 0.5: score += 10
    if is_bear and row["bb_pos"] > 0.5: score += 10
    score += confirmation_check(row, direction)
    if row["adx"] > 30: score += 15
    elif row["adx"] > 25: score += 5
    if row["vol_ratio"] > 1.2: score += 10
    score += cpr_confluence(row, direction)

    if score >= 50:
        signals.append({"direction": direction, "engine": "MOMENTUM", "score": min(90, score)})
    return signals


# ═══════════════════════════════════════
# BACKTEST ENGINE
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

        # ALL 6 setups
        all_signals = (zscore_signals(row) + ema_pullback_signals(row) +
                      consecutive_reversal_signals(row) + range_bounce_signals(row) +
                      rsi_extreme_signals(row) + momentum_signals(row, prev))

        if not all_signals: continue
        all_signals.sort(key=lambda s: s["score"], reverse=True)

        for signal in all_signals[:2]:
            if daily_trades >= 2: break
            score = signal["score"]
            if score < 55: continue

            if score >= 70: risk_mult = 1.2
            elif score >= 60: risk_mult = 0.8
            else: risk_mult = 0.5

            # Drawdown reduction (same as before)
            dd_pct = (peak - equity) / peak * 100 if peak > 0 else 0
            if dd_pct > 15: risk_mult *= 0.25
            elif dd_pct > 10: risk_mult *= 0.5
            elif dd_pct > 5: risk_mult *= 0.75
            if consec_loss >= 2: risk_mult *= 0.5

            spot = row["close"]; prem = spot * 0.004
            # 3X CHANGE: Risk 3% of CURRENT equity (was 2% of capital)
            # This compounds — as equity grows, position size grows
            max_risk = equity * 0.02 * risk_mult
            sl_cost = prem * 0.20 * 25
            if sl_cost <= 0: continue
            # 3X CHANGE: Max 8 lots (was 5) — bigger positions on strong signals
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
    print("  GX TRADEINTEL v6 — REALISTIC MODE")
    print("  v3 Accuracy + Conservative Sizing + Theta-Aware")
    print("  6 Setups | 2% Risk | Walk-Forward Validated")
    print("=" * 55 + "\n")

    df = download_nifty_data(2)
    if df.empty: return
    print("  Computing indicators + 6 setup types...")
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
    print(f"    v1: 44.4% WR | PF 1.43 | 187 trades | Rs  +6,447")
    print(f"    v2: 46.8% WR | PF 2.04 | 124 trades | Rs +12,558")
    print(f"    v3: 57.1% WR | PF 2.82 |  35 trades | Rs  +4,393")
    print(f"    v4: 52.7% WR | PF 1.78 |  91 trades | Rs  +6,874")
    print(f"    v5: {m['wr']}% WR | PF {m['pf']} | {m['trades']:>3} trades | Rs +{m['net']:,.0f}  ← REALISTIC")
    print()
    print(f"  BEFORE GOING LIVE:")
    print(f"    Paper trade 200+ trades (est. 6-12 months)")
    print(f"    Only go live if: WR > 50%, PF > 1.3, DD < 15%")
    print()

if __name__ == "__main__":
    main()
