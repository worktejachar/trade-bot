# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Robustness Testing + Strike Optimizer
==========================================================
Learned from:
  - marketcalls/vectorbt-backtesting-skills: noise injection, parameter sensitivity, entry delay
  - srikar-kodakandla: optimal strike selection across multiple combinations
  - Zerobha: CPR-based support/resistance for entry confirmation

Run: python3 robustness.py
"""
import numpy as np
import pandas as pd
from datetime import datetime


# ═══════════════════════════════════════
# 1. NOISE INJECTION TEST
# From: vectorbt-backtesting-skills/robustness-testing.md
# Adds random noise to prices, reruns backtest — if results collapse, strategy is overfit
# ═══════════════════════════════════════

def noise_injection_test(backtest_fn, df, noise_levels=[0.001, 0.002, 0.005], runs_per_level=5):
    """Add random noise to price data and check if strategy survives.
    
    If PF drops > 50% with 0.1% noise → strategy is overfit to exact prices.
    If PF stays > 1.0 with 0.5% noise → strategy is robust.
    """
    results = []

    # Baseline (no noise)
    base_trades, base_dd = backtest_fn(df)
    base_pf = _calc_pf(base_trades)
    results.append({"noise": 0, "pf": base_pf, "trades": len(base_trades), "label": "BASELINE"})

    for noise in noise_levels:
        pfs = []
        for _ in range(runs_per_level):
            noisy_df = df.copy()
            for col in ["open", "high", "low", "close"]:
                noisy_df[col] = noisy_df[col] * (1 + np.random.normal(0, noise, len(df)))
            # Fix OHLC consistency
            noisy_df["high"] = noisy_df[["open", "high", "close"]].max(axis=1)
            noisy_df["low"] = noisy_df[["open", "low", "close"]].min(axis=1)

            trades, dd = backtest_fn(noisy_df)
            pfs.append(_calc_pf(trades))

        avg_pf = np.mean(pfs)
        degradation = (base_pf - avg_pf) / base_pf * 100 if base_pf > 0 else 0
        results.append({
            "noise": noise * 100, "pf": round(avg_pf, 2),
            "trades": len(base_trades),
            "degradation": round(degradation, 1),
            "label": f"ROBUST" if avg_pf > 1.0 else "FRAGILE"
        })

    return results


# ═══════════════════════════════════════
# 2. PARAMETER SENSITIVITY TEST
# From: vectorbt-backtesting-skills/robustness-testing.md
# Varies strategy parameters slightly — stable systems show consistent results
# ═══════════════════════════════════════

def parameter_sensitivity(backtest_fn, df, param_name, base_value, variations=5, step_pct=10):
    """Test how sensitive the strategy is to parameter changes.
    
    If small changes (±10%) destroy performance → overfit.
    If results stay within 20% of base → robust.
    """
    results = []
    step = base_value * (step_pct / 100)

    for i in range(-variations, variations + 1):
        param_val = base_value + i * step
        if param_val <= 0: continue

        trades, dd = backtest_fn(df, **{param_name: param_val})
        pf = _calc_pf(trades)
        results.append({
            "param": param_name, "value": round(param_val, 2),
            "pf": round(pf, 2), "trades": len(trades),
            "is_base": i == 0,
        })

    return results


# ═══════════════════════════════════════
# 3. ENTRY DELAY TEST
# From: vectorbt-backtesting-skills/robustness-testing.md
# Delays entry by 1-3 bars — real trading always has execution delay
# ═══════════════════════════════════════

def entry_delay_test(backtest_fn, df, delays=[0, 1, 2, 3]):
    """Test impact of delayed entry (simulates real execution latency).
    
    In live trading, you never get the exact backtest entry price.
    If 1-bar delay drops PF below 1.0 → strategy has no real edge.
    """
    results = []
    for delay in delays:
        trades, dd = backtest_fn(df, entry_delay=delay)
        pf = _calc_pf(trades)
        results.append({
            "delay_bars": delay, "pf": round(pf, 2),
            "trades": len(trades), "dd": round(dd, 1),
        })
    return results


# ═══════════════════════════════════════
# 4. OPTIMAL STRIKE SELECTOR
# From: srikar-kodakandla/fully-automated-nifty-options-trading
# Checks multiple strike prices to find the best risk/reward
# ═══════════════════════════════════════

def optimal_strike(spot_price, option_chain, direction, risk_budget, lot_size=25):
    """Select the best strike price for entry.
    
    Instead of always picking ATM, check ITM-1, ATM, OTM-1, OTM-2
    and find which gives best risk/reward within budget.
    
    Args:
        spot_price: Current Nifty price
        option_chain: Dict of {strike: {"ce_premium", "pe_premium", "ce_oi", "pe_oi"}}
        direction: "BULL" or "BEAR"
        risk_budget: Max Rs to risk on this trade
        lot_size: 25 for Nifty
    
    Returns: Best strike with reasoning
    """
    if not option_chain:
        # Fallback: ATM
        atm = round(spot_price / 50) * 50
        return {"strike": atm, "type": "CE" if direction == "BULL" else "PE",
                "reason": "ATM (no chain data)", "premium_est": spot_price * 0.004}

    # Find ATM strike
    strikes = sorted(option_chain.keys())
    atm = min(strikes, key=lambda s: abs(s - spot_price))
    atm_idx = strikes.index(atm)

    candidates = []
    opt_type = "CE" if direction == "BULL" else "PE"
    prem_key = f"{opt_type.lower()}_premium"
    oi_key = f"{opt_type.lower()}_oi"

    # Check ATM, ITM-1, OTM-1, OTM-2
    for offset in [-1, 0, 1, 2]:
        idx = atm_idx + (offset if direction == "BULL" else -offset)
        if 0 <= idx < len(strikes):
            strike = strikes[idx]
            data = option_chain.get(strike, {})
            premium = data.get(prem_key, 0)
            oi = data.get(oi_key, 0)

            if premium <= 0: continue

            cost = premium * lot_size
            max_lots = max(1, int(risk_budget / (premium * 0.25 * lot_size))) if premium > 0 else 0
            
            # Score: balance between cost, OI (liquidity), and delta proxy
            distance = abs(strike - spot_price) / spot_price * 100
            score = 0
            if distance < 0.3: score += 30  # Near ATM = good delta
            elif distance < 0.6: score += 20
            else: score += 10
            
            if oi > 0: score += min(20, int(oi / 100000))  # Liquidity bonus
            if cost <= risk_budget * 0.5: score += 15  # Affordable
            if premium < 200: score += 10  # Cheap = high leverage

            candidates.append({
                "strike": strike, "premium": premium, "oi": oi,
                "cost_per_lot": cost, "max_lots": max_lots,
                "distance_pct": round(distance, 2), "score": score,
                "type": opt_type,
            })

    if not candidates:
        return {"strike": atm, "type": opt_type, "reason": "No valid candidates",
                "premium_est": spot_price * 0.004}

    # Pick highest score
    best = max(candidates, key=lambda c: c["score"])
    return {
        "strike": best["strike"], "type": best["type"],
        "premium": best["premium"], "oi": best["oi"],
        "max_lots": best["max_lots"], "cost_per_lot": best["cost_per_lot"],
        "reason": f"Score {best['score']}: {best['distance_pct']}% from ATM, OI {best['oi']:,}",
    }


# ═══════════════════════════════════════
# 5. WALK-FORWARD EFFICIENCY
# From: vectorbt-backtesting-skills/walk-forward.md
# Measures how well in-sample performance predicts out-of-sample
# ═══════════════════════════════════════

def walk_forward_efficiency(backtest_fn, df, n_folds=5):
    """Rolling walk-forward test with efficiency ratio.
    
    WFE = Out-of-sample PF / In-sample PF
    WFE > 0.5 = strategy generalizes well
    WFE < 0.3 = likely overfit
    """
    fold_size = len(df) // (n_folds + 1)
    results = []

    for i in range(n_folds):
        train_start = i * fold_size
        train_end = train_start + fold_size * 2
        test_end = min(train_end + fold_size, len(df))

        if test_end > len(df): break

        train_df = df.iloc[train_start:train_end]
        test_df = df.iloc[train_end:test_end]

        train_trades, _ = backtest_fn(train_df)
        test_trades, _ = backtest_fn(test_df)

        train_pf = _calc_pf(train_trades)
        test_pf = _calc_pf(test_trades)
        wfe = test_pf / train_pf if train_pf > 0 else 0

        results.append({
            "fold": i + 1, "train_pf": round(train_pf, 2),
            "test_pf": round(test_pf, 2), "wfe": round(wfe, 2),
            "train_trades": len(train_trades), "test_trades": len(test_trades),
        })

    if results:
        avg_wfe = np.mean([r["wfe"] for r in results])
        print(f"\n  Walk-Forward Efficiency: {avg_wfe:.2f}")
        if avg_wfe > 0.5:
            print("  ROBUST: Strategy generalizes well out-of-sample")
        elif avg_wfe > 0.3:
            print("  ACCEPTABLE: Some degradation but still valid")
        else:
            print("  WARNING: Possible overfit — out-of-sample much worse")

    return results


# ═══════════════════════════════════════
# 6. CPR CONFLUENCE CHECKER
# From: Zerobha repo — CPR + VWAP strategy
# Checks if trade entry aligns with pivot levels
# ═══════════════════════════════════════

def cpr_confluence(price, pivot, tc, bc, r1, s1, atr_val):
    """Check if entry price has CPR level support.
    
    Returns score 0-30 based on proximity to key levels.
    """
    score = 0
    tolerance = atr_val * 0.3 if atr_val > 0 else 5

    # Near pivot = strong reference
    if abs(price - pivot) < tolerance: score += 15
    # Near support (bullish)
    if abs(price - s1) < tolerance: score += 20
    # Near resistance (bearish entry)
    if abs(price - r1) < tolerance: score += 20
    # Within CPR range = indecision zone
    if min(tc, bc) <= price <= max(tc, bc): score += 10
    # CPR narrow = breakout likely
    cpr_width = abs(tc - bc) / price * 100
    if cpr_width < 0.3: score += 10  # Narrow CPR

    return min(30, score)


# ═══════════════════════════════════════
# HELPER
# ═══════════════════════════════════════

def _calc_pf(trades):
    if not trades: return 0
    wins = sum(t.get("pnl", t.get("pnl_net", 0)) for t in trades if t["result"] == "WIN")
    losses = abs(sum(t.get("pnl", t.get("pnl_net", 0)) for t in trades if t["result"] == "LOSS"))
    return round(wins / losses, 2) if losses > 0 else 999


# ═══════════════════════════════════════
# MAIN — Run all robustness tests
# ═══════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  GX TRADEINTEL — ROBUSTNESS TESTING")
    print("  Noise injection | Parameter sensitivity | Entry delay")
    print("=" * 55)
    print()
    print("  Run backtest.py first, then import robustness tests")
    print("  into your strategy validation workflow.")
    print()
    print("  Usage:")
    print("    from robustness import noise_injection_test, optimal_strike")
    print("    results = noise_injection_test(my_backtest_fn, df)")
    print()
