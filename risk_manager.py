# -*- coding: utf-8 -*-
"""
GX TradeIntel v4 — Risk Manager
==================================
Sources: trade-psychology-capital (full), trading-intelligence §5, backtesting-performance §2
The survival engine. Revenge trading guard, FOMO block, trailing ladder, psychology checks.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass

import config

logger = logging.getLogger("GXTradeIntel.Risk")


@dataclass
class Position:
    symbol: str
    token: str
    direction: str
    entry_price: float
    quantity: int
    stop_loss: float
    target_1: float
    target_2: float
    order_id: str
    entry_time: datetime
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: str = ""
    pnl: float = 0
    highest_premium: float = 0
    trailing_active: bool = False

    @property
    def is_open(self): return self.exit_price is None

    @property
    def holding_minutes(self): return int((datetime.now() - self.entry_time).total_seconds() / 60)


class RiskManager:
    def __init__(self):
        self.positions: List[Position] = []
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_wins = 0
        self.daily_losses = 0
        self.consecutive_losses = 0
        self.last_loss_time: Optional[datetime] = None
        self.weekly_pnl = 0.0
        self.total_trades_lifetime = 0  # For scaling ladder

    # ── PRE-TRADE CHECKS [trade-psychology §4-6] ──

    def can_trade(self) -> tuple:
        checks = []

        # Max daily trades [trading-intelligence §1]
        if self.daily_trades >= config.MAX_TRADES_PER_DAY:
            return False, f"Daily limit ({config.MAX_TRADES_PER_DAY} trades)"

        # Daily loss limit [trade-psychology §1]
        if self.daily_pnl <= -(config.MAX_DAILY_LOSS * 0.8):
            return False, f"Daily loss limit (80% of ₹{config.MAX_DAILY_LOSS:,.0f} hit)"

        # Open position check
        if any(p.is_open for p in self.positions):
            return False, "Already have open position"

        # Time check
        now = datetime.now().time()
        if now > config.STRATEGY["no_new_entry_after"]:
            return False, "Past 14:30 — no entries"

        # ── PSYCHOLOGY CHECKS [trade-psychology §4] ──

        if config.PSYCHOLOGY["red_flag_checks"]:
            # Revenge trading guard: cooldown after loss
            if self.last_loss_time and config.PSYCHOLOGY["revenge_trade_block"]:
                cooldown = timedelta(minutes=config.PSYCHOLOGY["cooldown_after_loss_streak"])
                if datetime.now() - self.last_loss_time < cooldown:
                    remaining = cooldown - (datetime.now() - self.last_loss_time)
                    return False, f"Revenge cooldown: {remaining.seconds//60}min left"

            # Consecutive loss pause
            if self.consecutive_losses >= config.PSYCHOLOGY["max_consecutive_losses"]:
                return False, f"{self.consecutive_losses} consecutive losses — stopping for today"

        return True, "Clear to trade"

    # ── POSITION SIZING [trade-psychology §2] ──

    def calculate_position_size(self, premium: float, lot_size: int, vix_multiplier: float = 1.0) -> tuple:
        """Dynamic position sizing — scales with ANY capital.
        
        ₹10K:  1 lot (25 qty)
        ₹50K:  2-3 lots (50-75 qty)  
        ₹1L:   4-5 lots (100-125 qty)
        ₹5L:   10-15 lots
        ₹10L+: 20+ lots
        """
        if premium <= 0:
            return 0, 0, "Invalid premium"

        # Determine risk % based on experience
        if self.total_trades_lifetime < 20:
            risk_pct = config.MAX_RISK_PER_TRADE_PCT * 0.6  # 60% of normal risk while learning
        else:
            risk_pct = config.MAX_RISK_PER_TRADE_PCT

        # VIX adjustment: halve size in volatile markets
        risk_pct *= vix_multiplier

        risk_amount = config.TOTAL_CAPITAL * (risk_pct / 100)
        max_spend = config.MAX_CAPITAL_PER_TRADE
        cost_per_lot = premium * lot_size

        if cost_per_lot > max_spend:
            return 0, cost_per_lot, f"1 lot ₹{cost_per_lot:,.0f} > max ₹{max_spend:,.0f}"

        # How many lots can we afford?
        max_lots_by_capital = max(1, int(max_spend / cost_per_lot))

        # How many lots within risk limit?
        sl_per_lot = premium * (config.STOP_LOSS_PCT / 100) * lot_size
        max_lots_by_risk = max(1, int(risk_amount / sl_per_lot)) if sl_per_lot > 0 else 1

        # Take the smaller of the two
        lots = min(max_lots_by_capital, max_lots_by_risk)
        quantity = lots * lot_size
        total_cost = cost_per_lot * lots
        total_risk = sl_per_lot * lots

        return quantity, total_cost, (
            f"OK: {lots} lot(s) × {lot_size} = {quantity} qty | "
            f"Cost: ₹{total_cost:,.0f} | Risk: ₹{total_risk:,.0f} ({risk_pct:.1f}%)"
        )

    # ── EXIT CHECKS — MTM BASED [Feature 3: Mark-to-Market targets] ──

    def check_exit(self, pos: Position, current: float) -> tuple:
        if not pos.is_open:
            return False, ""

        pos.highest_premium = max(pos.highest_premium, current)
        pnl_pct = ((current - pos.entry_price) / pos.entry_price) * 100

        # MTM P&L in actual rupees (what really matters)
        mtm_pnl = (current - pos.entry_price) * pos.quantity
        mtm_peak = (pos.highest_premium - pos.entry_price) * pos.quantity

        # 1. Hard stop loss — MTM based
        # If actual rupee loss exceeds risk limit, EXIT immediately
        max_loss_rupees = config.MAX_RISK_PER_TRADE
        if mtm_pnl <= -max_loss_rupees:
            return True, f"STOP LOSS MTM (₹{mtm_pnl:,.0f} loss, limit ₹{max_loss_rupees:,.0f})"

        # Also check percentage SL as backup
        if pnl_pct <= -config.STOP_LOSS_PCT:
            return True, f"STOP LOSS ({pnl_pct:.1f}%)"

        # 2. Profit Target — MTM based
        # Target = risk × reward multiplier (default 2x risk)
        target_rupees = max_loss_rupees * 2.0  # 1:2 risk-reward minimum
        if mtm_pnl >= target_rupees:
            return True, f"TARGET MTM (+₹{mtm_pnl:,.0f}, target was ₹{target_rupees:,.0f})"

        # Also check percentage target
        if pnl_pct >= config.PROFIT_TARGET_1_PCT:
            return True, f"TARGET 1 (+{pnl_pct:.1f}%, ₹{mtm_pnl:,.0f})"

        if pnl_pct >= config.PROFIT_TARGET_2_PCT:
            return True, f"TARGET 2 (+{pnl_pct:.1f}%, ₹{mtm_pnl:,.0f})"

        # 3. Trailing stop — MTM based
        if mtm_pnl >= max_loss_rupees * 0.5:  # Activate trail at 0.5x risk profit
            pos.trailing_active = True

        if pnl_pct >= config.TRAILING_ACTIVATION_PCT:
            pos.trailing_active = True
            if current <= pos.entry_price:
                return True, f"TRAILING: Back to breakeven (₹{mtm_pnl:,.0f})"

        if pos.trailing_active and pos.highest_premium > 0:
            # Trail from peak — if dropped 40% of unrealized gains, exit
            if mtm_peak > 0 and mtm_pnl < mtm_peak * 0.6:
                return True, f"TRAILING MTM: Gave back 40% of peak ₹{mtm_peak:,.0f} → now ₹{mtm_pnl:,.0f}"

            drop = ((current - pos.highest_premium) / pos.highest_premium) * 100
            if drop <= -config.TRAILING_DROP_FROM_PEAK:
                return True, f"TRAILING: -{abs(drop):.1f}% from peak (₹{mtm_pnl:,.0f})"

        # 5. Time stop [trading-intelligence §5]
        if pos.holding_minutes >= config.TIME_STOP_MINUTES and pnl_pct < 5:
            return True, f"TIME STOP ({pos.holding_minutes}min, {pnl_pct:+.1f}%)"

        # 6. Square off
        if datetime.now().time() >= config.SQUARE_OFF:
            return True, "SQUARE OFF 15:20"

        return False, ""

    # ── RECORD KEEPING ──

    def record_exit(self, pos: Position, price: float, reason: str):
        pos.exit_price = price
        pos.exit_time = datetime.now()
        pos.exit_reason = reason
        pos.pnl = (price - pos.entry_price) * pos.quantity
        self.daily_pnl += pos.pnl
        self.weekly_pnl += pos.pnl

        if pos.pnl > 0:
            self.daily_wins += 1
            self.consecutive_losses = 0
        else:
            self.daily_losses += 1
            self.consecutive_losses += 1
            self.last_loss_time = datetime.now()

        self.total_trades_lifetime += 1

    def record_trade(self):
        self.daily_trades += 1

    def daily_stats(self) -> dict:
        total = self.daily_wins + self.daily_losses
        wr = (self.daily_wins / total * 100) if total > 0 else 0
        return {"trades": self.daily_trades, "wins": self.daily_wins, "losses": self.daily_losses,
                "win_rate": round(wr, 1), "pnl": round(self.daily_pnl, 2),
                "consecutive_losses": self.consecutive_losses,
                "capital_after": round(config.TOTAL_CAPITAL + self.daily_pnl, 2)}

    def reset_daily(self):
        self.daily_trades = 0
        self.daily_pnl = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.positions = [p for p in self.positions if p.is_open]

    # ── GRADUATION CHECK [backtesting-performance §4] ──

    def paper_graduation_check(self, all_trades: list) -> dict:
        """Check if paper trading results meet live trading criteria."""
        bc = config.BACKTEST
        if len(all_trades) < bc["min_trades_for_live"]:
            return {"ready": False, "reason": f"Need {bc['min_trades_for_live']} trades, have {len(all_trades)}"}

        winners = [t for t in all_trades if t.get("pnl", 0) > 0]
        losers = [t for t in all_trades if t.get("pnl", 0) <= 0]
        wr = len(winners) / len(all_trades) * 100 if all_trades else 0
        gross_win = sum(t["pnl"] for t in winners)
        gross_loss = abs(sum(t["pnl"] for t in losers)) or 1
        pf = gross_win / gross_loss

        checks = {
            "win_rate": {"value": round(wr, 1), "target": bc["min_win_rate"], "pass": wr >= bc["min_win_rate"]},
            "profit_factor": {"value": round(pf, 2), "target": bc["min_profit_factor"], "pass": pf >= bc["min_profit_factor"]},
            "total_trades": {"value": len(all_trades), "target": bc["min_trades_for_live"], "pass": True},
            "net_pnl": {"value": round(gross_win - gross_loss + 1, 2), "target": "> 0", "pass": gross_win > gross_loss},
        }

        all_pass = all(c["pass"] for c in checks.values())
        return {"ready": all_pass, "checks": checks,
                "recommendation": "✅ Ready for live!" if all_pass else "❌ Continue paper trading"}
