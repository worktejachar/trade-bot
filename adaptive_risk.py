# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Adaptive Risk Engine
==========================================
Everything ChatGPT suggested, built into working code:
1. Adaptive risk formula (regime x PF x DD x score)
2. Strategy auto-disable based on live PF
3. VWAP Stretch Score (Z-score for mean reversion)
4. Capital scaling tiers (learning → validation → scaling)
5. Drawdown-based position reduction
6. Worst-case stress test (clustered losses)
7. Trade flow pipeline tracking
8. Strategy performance registry
"""
import logging
import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, Optional

import config

logger = logging.getLogger("GXTradeIntel.AdaptiveRisk")


# ═══════════════════════════════════════
# 1. ADAPTIVE RISK FORMULA
# ═══════════════════════════════════════

class AdaptiveRiskEngine:
    """Dynamic risk sizing based on market state + system state.
    
    Final Risk = Base Risk x Regime Factor x Strategy Factor x DD Factor x Score Factor
    
    This replaces fixed 2.5% risk with intelligent scaling.
    """

    def __init__(self):
        self.strategy_registry = StrategyRegistry()
        self.trade_flow = TradeFlowTracker()
        self.capital_tier = CapitalTier()
        self.peak_equity = config.TOTAL_CAPITAL
        self.current_equity = config.TOTAL_CAPITAL

    def calculate_risk(self, regime: str, strategy: str, score: int, 
                       current_equity: float = None) -> Dict:
        """Calculate adaptive risk for a trade."""
        equity = current_equity or self.current_equity
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)

        # Base risk from capital tier
        base_pct = self.capital_tier.get_risk_pct(equity)
        base_risk = equity * (base_pct / 100)

        # 1. Regime factor
        regime_factors = {
            "RANGING": 1.2,     # Mean reversion works best here
            "TRENDING": 1.0,    # Momentum territory
            "VOLATILE": 0.6,    # Careful
            "UNCLEAR": 0.3,     # Barely trade
        }
        regime_f = regime_factors.get(regime, 0.5)

        # 2. Strategy factor (based on live PF)
        strat_stats = self.strategy_registry.get_stats(strategy)
        pf = strat_stats.get("profit_factor", 1.0)
        if pf >= 2.0: strat_f = 1.2
        elif pf >= 1.5: strat_f = 1.0
        elif pf >= 1.2: strat_f = 0.7
        elif pf >= 1.0: strat_f = 0.5
        else: strat_f = 0  # DISABLED

        # Check if strategy should be disabled
        if strat_stats.get("trades", 0) >= 10 and pf < 1.0:
            logger.warning(f"Strategy {strategy} DISABLED (PF {pf:.2f} < 1.0 after {strat_stats['trades']} trades)")
            return {"risk": 0, "reason": f"Strategy {strategy} disabled (PF {pf:.2f})", "action": "SKIP"}

        # 3. Drawdown factor
        dd_pct = self._current_drawdown()
        if dd_pct < 5: dd_f = 1.0
        elif dd_pct < 10: dd_f = 0.75
        elif dd_pct < 15: dd_f = 0.5
        elif dd_pct < 20: dd_f = 0.25
        else:
            logger.critical(f"Drawdown {dd_pct:.1f}% > 20% — STOP TRADING")
            return {"risk": 0, "reason": f"Drawdown {dd_pct:.1f}% exceeds 20%", "action": "STOP"}

        # 4. Score factor
        if score >= 75: score_f = 1.2
        elif score >= 60: score_f = 1.0
        elif score >= 45: score_f = 0.6
        else: score_f = 0.3

        # Final calculation
        final_risk = base_risk * regime_f * strat_f * dd_f * score_f

        # Hard cap: never exceed 2% of equity
        max_risk = equity * 0.02
        final_risk = min(final_risk, max_risk)

        # Floor: minimum ₹50 to be worth trading
        if final_risk < 50:
            return {"risk": 0, "reason": "Risk too small to be meaningful", "action": "SKIP"}

        result = {
            "risk": round(final_risk, 2),
            "base_risk": round(base_risk, 2),
            "regime_factor": regime_f,
            "strategy_factor": strat_f,
            "dd_factor": dd_f,
            "score_factor": score_f,
            "drawdown_pct": round(dd_pct, 1),
            "tier": self.capital_tier.current_tier(equity),
            "action": "TRADE",
            "reason": f"Adaptive: {base_pct}% x {regime_f} x {strat_f} x {dd_f} x {score_f} = Rs {final_risk:.0f}",
        }

        logger.info(f"Adaptive Risk: Rs {final_risk:.0f} | {result['reason']}")
        return result

    def _current_drawdown(self) -> float:
        if self.peak_equity <= 0: return 0
        return (self.peak_equity - self.current_equity) / self.peak_equity * 100

    def update_equity(self, pnl: float):
        self.current_equity += pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)

    def record_trade(self, strategy: str, result: str, pnl: float, score: int):
        """Record trade for strategy tracking and trade flow."""
        self.strategy_registry.record(strategy, result, pnl)
        self.trade_flow.record_trade(strategy, score, result, pnl)
        self.update_equity(pnl)


# ═══════════════════════════════════════
# 2. STRATEGY AUTO-DISABLE REGISTRY
# ═══════════════════════════════════════

class StrategyRegistry:
    """Tracks live performance per strategy. Auto-disables losers."""

    REGISTRY_FILE = "logs/strategy_registry.json"

    def __init__(self):
        self.strategies = self._load()

    def _load(self):
        if os.path.exists(self.REGISTRY_FILE):
            try:
                with open(self.REGISTRY_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        os.makedirs("logs", exist_ok=True)
        with open(self.REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.strategies, f, indent=2)

    def record(self, strategy: str, result: str, pnl: float):
        if strategy not in self.strategies:
            self.strategies[strategy] = {
                "trades": 0, "wins": 0, "losses": 0,
                "gross_profit": 0, "gross_loss": 0,
                "status": "ACTIVE", "last_updated": "",
            }

        s = self.strategies[strategy]
        s["trades"] += 1
        if result == "WIN":
            s["wins"] += 1
            s["gross_profit"] += pnl
        else:
            s["losses"] += 1
            s["gross_loss"] += abs(pnl)

        # Calculate PF
        s["profit_factor"] = round(s["gross_profit"] / s["gross_loss"], 2) if s["gross_loss"] > 0 else 999
        s["win_rate"] = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0

        # Auto-disable check
        if s["trades"] >= 10 and s["profit_factor"] < 1.0:
            s["status"] = "DISABLED"
            logger.warning(f"AUTO-DISABLED: {strategy} (PF {s['profit_factor']} after {s['trades']} trades)")
        elif s["trades"] >= 5 and s["profit_factor"] >= 1.2:
            s["status"] = "ACTIVE"

        s["last_updated"] = datetime.now().isoformat()
        self._save()

    def get_stats(self, strategy: str) -> Dict:
        return self.strategies.get(strategy, {"trades": 0, "profit_factor": 1.0, "status": "ACTIVE"})

    def is_active(self, strategy: str) -> bool:
        return self.get_stats(strategy).get("status", "ACTIVE") == "ACTIVE"

    def get_summary(self) -> str:
        lines = ["Strategy         Trades  WR%    PF    Status"]
        lines.append("-" * 48)
        for name, s in self.strategies.items():
            lines.append(f"{name:<17} {s['trades']:>5}  {s.get('win_rate',0):>5.1f}  {s.get('profit_factor',0):>5.2f}  {s['status']}")
        return "\n".join(lines)


# ═══════════════════════════════════════
# 3. VWAP STRETCH SCORE
# ═══════════════════════════════════════

def vwap_stretch_score(price: float, vwap: float, atr: float) -> Dict:
    """Z-Score: how far price is from fair value in ATR units.
    
    Z > +1.5 → overbought, buy PE
    Z < -1.5 → oversold, buy CE
    Z > +2.0 → strong signal
    """
    if atr <= 0 or vwap <= 0:
        return {"z_score": 0, "stretch_score": 0, "signal": "NONE"}

    z = (price - vwap) / atr

    # Stretch score (0-100)
    abs_z = abs(z)
    if abs_z >= 2.0: stretch = 30
    elif abs_z >= 1.5: stretch = 20
    elif abs_z >= 1.0: stretch = 10
    else: stretch = 0

    signal = "NONE"
    if z < -1.5: signal = "BUY_CE"
    elif z < -1.0: signal = "POSSIBLE_CE"
    elif z > 1.5: signal = "BUY_PE"
    elif z > 1.0: signal = "POSSIBLE_PE"

    return {
        "z_score": round(z, 2),
        "stretch_score": stretch,
        "signal": signal,
        "description": f"Price is {abs_z:.1f} ATR {'above' if z > 0 else 'below'} fair value",
    }


# ═══════════════════════════════════════
# 4. CAPITAL SCALING TIERS
# ═══════════════════════════════════════

class CapitalTier:
    """Risk % scales with capital level and experience."""

    TIERS = {
        "LEARNING": {"min": 0, "max": 25000, "risk_pct": 1.5, "max_trades": 2},
        "VALIDATION": {"min": 25000, "max": 100000, "risk_pct": 2.0, "max_trades": 3},
        "SCALING": {"min": 100000, "max": 500000, "risk_pct": 1.5, "max_trades": 4},
        "PROFESSIONAL": {"min": 500000, "max": float("inf"), "risk_pct": 1.0, "max_trades": 5},
    }

    def current_tier(self, capital: float) -> str:
        for name, tier in self.TIERS.items():
            if tier["min"] <= capital < tier["max"]:
                return name
        return "LEARNING"

    def get_risk_pct(self, capital: float) -> float:
        tier_name = self.current_tier(capital)
        return self.TIERS[tier_name]["risk_pct"]

    def get_max_trades(self, capital: float) -> int:
        tier_name = self.current_tier(capital)
        return self.TIERS[tier_name]["max_trades"]

    def get_info(self, capital: float) -> Dict:
        tier_name = self.current_tier(capital)
        tier = self.TIERS[tier_name]
        return {
            "tier": tier_name,
            "risk_pct": tier["risk_pct"],
            "max_trades": tier["max_trades"],
            "risk_amount": round(capital * tier["risk_pct"] / 100, 2),
        }


# ═══════════════════════════════════════
# 5. DRAWDOWN-BASED POSITION REDUCTION
# ═══════════════════════════════════════

class DrawdownGuard:
    """Automatically reduces position size as drawdown increases."""

    LEVELS = [
        {"dd_pct": 5, "action": "NORMAL", "size_mult": 1.0, "message": "Normal trading"},
        {"dd_pct": 10, "action": "REDUCE", "size_mult": 0.75, "message": "Drawdown 10% — reducing size 25%"},
        {"dd_pct": 15, "action": "HALF", "size_mult": 0.5, "message": "Drawdown 15% — halving positions"},
        {"dd_pct": 20, "action": "STOP", "size_mult": 0, "message": "Drawdown 20% — STOP TRADING"},
    ]

    @staticmethod
    def check(peak_equity: float, current_equity: float) -> Dict:
        if peak_equity <= 0:
            return DrawdownGuard.LEVELS[0]

        dd = (peak_equity - current_equity) / peak_equity * 100

        for level in reversed(DrawdownGuard.LEVELS):
            if dd >= level["dd_pct"]:
                if level["action"] == "STOP":
                    logger.critical(f"DRAWDOWN GUARD: {dd:.1f}% — STOPPING ALL TRADING")
                elif level["action"] != "NORMAL":
                    logger.warning(f"DRAWDOWN GUARD: {dd:.1f}% — {level['message']}")
                return {**level, "current_dd": round(dd, 1)}

        return {**DrawdownGuard.LEVELS[0], "current_dd": round(dd, 1)}


# ═══════════════════════════════════════
# 6. WORST-CASE STRESS TEST
# ═══════════════════════════════════════

def stress_test(avg_win: float = 300, avg_loss: float = 150, win_rate: float = 0.58,
                capital: float = 10000, simulations: int = 5):
    """Simulate worst-case clustered loss scenarios."""
    results = []

    scenarios = [
        ("10 consecutive losses", ["L"] * 10 + ["W", "L"] * 10 + ["W"] * 8),
        ("Choppy market (alternating)", ["W", "L", "L", "W", "L", "L", "W", "L"] * 8),
        ("Slow bleed", ["W", "L", "L", "L"] * 15),
        ("Recovery after crash", ["L"] * 8 + ["W"] * 5 + ["L"] * 4 + ["W"] * 12),
        ("Random realistic", None),  # Monte Carlo
    ]

    for name, sequence in scenarios:
        eq = capital; peak = capital; max_dd = 0

        if sequence is None:
            # Random
            sequence = []
            for _ in range(60):
                sequence.append("W" if np.random.random() < win_rate else "L")

        for trade in sequence:
            if trade == "W":
                eq += avg_win * (0.8 + np.random.random() * 0.4)
            else:
                eq -= avg_loss * (0.8 + np.random.random() * 0.4)
            peak = max(peak, eq)
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        results.append({
            "scenario": name,
            "final_equity": round(eq, 0),
            "max_drawdown": round(max_dd, 1),
            "survived": eq > capital * 0.5,
            "return_pct": round((eq - capital) / capital * 100, 1),
        })

    return results


# ═══════════════════════════════════════
# 7. TRADE FLOW TRACKER
# ═══════════════════════════════════════

class TradeFlowTracker:
    """Tracks the full pipeline: signals → scored → rejected → executed."""

    def __init__(self):
        self.signals_detected = 0
        self.signals_scored = 0
        self.signals_rejected = 0
        self.trades_executed = 0
        self.trades_won = 0
        self.trades_lost = 0
        self.daily_reset_date = None

    def record_signal(self):
        self._check_reset()
        self.signals_detected += 1

    def record_scored(self, passed: bool):
        self._check_reset()
        self.signals_scored += 1
        if not passed:
            self.signals_rejected += 1

    def record_trade(self, strategy: str, score: int, result: str, pnl: float):
        self._check_reset()
        self.trades_executed += 1
        if result == "WIN": self.trades_won += 1
        else: self.trades_lost += 1

    def get_summary(self) -> Dict:
        conv = self.trades_executed / self.signals_detected * 100 if self.signals_detected > 0 else 0
        return {
            "signals_detected": self.signals_detected,
            "signals_scored": self.signals_scored,
            "signals_rejected": self.signals_rejected,
            "trades_executed": self.trades_executed,
            "trades_won": self.trades_won,
            "trades_lost": self.trades_lost,
            "conversion_rate": round(conv, 1),
        }

    def get_telegram_text(self) -> str:
        s = self.get_summary()
        return (
            f"Signals: {s['signals_detected']} | "
            f"Scored: {s['signals_scored']} | "
            f"Rejected: {s['signals_rejected']} | "
            f"Traded: {s['trades_executed']} ({s['conversion_rate']}%)"
        )

    def _check_reset(self):
        today = datetime.now().date()
        if self.daily_reset_date != today:
            self.signals_detected = 0
            self.signals_scored = 0
            self.signals_rejected = 0
            self.trades_executed = 0
            self.trades_won = 0
            self.trades_lost = 0
            self.daily_reset_date = today
