# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Post-Market Analyzer
==========================================
ChatGPT said: "You're not measuring regime accuracy."
Now we do. Every day. With hard numbers.

Runs after market close to:
1. Validate if regime prediction was correct
2. Calculate all performance metrics
3. Track equity curve
4. Generate daily report card
"""
import logging
import csv
import os
from datetime import datetime
from typing import List, Dict

import numpy as np
import pandas as pd

import config

logger = logging.getLogger("GXTradeIntel.PostMarket")


class PostMarketAnalyzer:
    """Post-market validation and performance tracking."""

    def __init__(self):
        self.regime_log_file = f"{config.LOG_DIR}/regime_accuracy.csv"
        self.performance_file = f"{config.LOG_DIR}/performance.csv"
        self.equity_file = f"{config.LOG_DIR}/equity_curve.csv"

    # ── Regime Accuracy [ChatGPT criticism: "you're guessing"] ──

    def validate_regime(self, predicted_regime: str, df_daily: pd.DataFrame) -> Dict:
        """After market close, check if our regime prediction was correct."""
        if df_daily is None or df_daily.empty:
            return {"predicted": predicted_regime, "actual": "UNKNOWN", "correct": False}

        today = df_daily.iloc[-1]
        day_open = today["open"]
        day_close = today["close"]
        day_high = today["high"]
        day_low = today["low"]
        day_range = day_high - day_low
        net_move = abs(day_close - day_open)
        net_move_pct = net_move / day_open * 100

        # Count reversals (direction changes)
        if len(df_daily) > 10:
            intraday_closes = df_daily.tail(10)["close"]
            direction_changes = sum(1 for i in range(1, len(intraday_closes))
                                   if (intraday_closes.iloc[i] > intraday_closes.iloc[i-1]) !=
                                      (intraday_closes.iloc[i-1] > intraday_closes.iloc[max(0,i-2)]))
        else:
            direction_changes = 0

        # Classify actual regime
        if net_move_pct > 1.0 and direction_changes < 4:
            actual = "TRENDING"
        elif net_move_pct < 0.5 and direction_changes >= 4:
            actual = "RANGING"
        elif day_range / day_open * 100 > 2.0:
            actual = "VOLATILE"
        else:
            actual = "RANGING"  # Default for ambiguous

        correct = predicted_regime == actual
        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "predicted": predicted_regime,
            "actual": actual,
            "correct": correct,
            "net_move_pct": round(net_move_pct, 2),
            "range_pct": round(day_range / day_open * 100, 2),
            "reversals": direction_changes,
        }

        # Log
        self._log_regime(result)
        emoji = "✅" if correct else "❌"
        logger.info(f"{emoji} Regime: Predicted {predicted_regime} | Actual {actual} | Move {net_move_pct:.2f}%")

        return result

    def get_regime_accuracy(self, days: int = 30) -> Dict:
        """Calculate regime prediction accuracy over N days."""
        if not os.path.exists(self.regime_log_file):
            return {"accuracy": 0, "total_days": 0}

        df = pd.read_csv(self.regime_log_file)
        recent = df.tail(days)
        if recent.empty:
            return {"accuracy": 0, "total_days": 0}

        correct = recent["correct"].sum()
        total = len(recent)
        accuracy = correct / total * 100

        # Profit-weighted accuracy (ChatGPT's suggestion)
        return {
            "accuracy": round(accuracy, 1),
            "correct": int(correct),
            "total_days": total,
            "by_regime": {
                r: {
                    "predicted": int((recent["predicted"] == r).sum()),
                    "correct": int(((recent["predicted"] == r) & recent["correct"]).sum()),
                }
                for r in ["TRENDING", "RANGING", "VOLATILE", "UNCLEAR"]
            }
        }

    # ── Performance Metrics [ChatGPT: "investor-grade metrics"] ──

    def calculate_full_metrics(self, trades: List[Dict], initial_capital: float = None) -> Dict:
        """Complete performance metrics — Sharpe, Sortino, Calmar, Expectancy, everything."""
        capital = initial_capital or config.TOTAL_CAPITAL

        if not trades:
            return {"status": "NO_TRADES"}

        pnls = [t.get("pnl", 0) for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        total = len(pnls)
        w = len(winners)
        l = len(losers)
        wr = w / total * 100 if total else 0

        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        net = gross_profit - gross_loss
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win = gross_profit / w if w else 0
        avg_loss = gross_loss / l if l else 0

        # Expectancy
        expectancy = (wr/100 * avg_win) - ((1-wr/100) * avg_loss)

        # Equity curve
        equity = [capital]
        peak = capital
        max_dd = 0
        max_dd_duration = 0
        current_dd_start = 0

        for pnl in pnls:
            equity.append(equity[-1] + pnl)
            if equity[-1] > peak:
                peak = equity[-1]
                current_dd_start = len(equity) - 1
            dd = (peak - equity[-1]) / peak * 100
            max_dd = max(max_dd, dd)

        # Sharpe Ratio (annualized, assuming 250 trading days)
        daily_returns = [pnls[i] / equity[i] for i in range(len(pnls))] if equity else []
        if daily_returns and len(daily_returns) > 1:
            mean_return = np.mean(daily_returns)
            std_return = np.std(daily_returns)
            sharpe = (mean_return / std_return) * np.sqrt(250) if std_return > 0 else 0
        else:
            sharpe = 0

        # Sortino (only downside deviation)
        neg_returns = [r for r in daily_returns if r < 0]
        if neg_returns:
            downside_std = np.std(neg_returns)
            sortino = (np.mean(daily_returns) / downside_std) * np.sqrt(250) if downside_std > 0 else 0
        else:
            sortino = 0

        # Calmar (return / max drawdown)
        total_return_pct = (equity[-1] - capital) / capital * 100
        calmar = total_return_pct / max_dd if max_dd > 0 else 0

        # Recovery factor
        recovery = net / (capital * max_dd / 100) if max_dd > 0 else 0

        # Consecutive losses
        max_consec_loss = 0
        current_streak = 0
        for pnl in pnls:
            if pnl <= 0:
                current_streak += 1
                max_consec_loss = max(max_consec_loss, current_streak)
            else:
                current_streak = 0

        return {
            "total_trades": total,
            "wins": w, "losses": l,
            "win_rate": round(wr, 1),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "net_profit": round(net, 2),
            "profit_factor": round(pf, 2),
            "avg_winner": round(avg_win, 2),
            "avg_loser": round(avg_loss, 2),
            "expectancy": round(expectancy, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "max_consecutive_losses": max_consec_loss,
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "recovery_factor": round(recovery, 2),
            "total_return_pct": round(total_return_pct, 2),
            "final_equity": round(equity[-1], 2),
            "equity_curve": equity,
        }

    # ── Daily Report Card ──

    def generate_report_card(self, regime_result: Dict, daily_stats: Dict, metrics: Dict) -> str:
        """Generate end-of-day report card for Telegram."""
        r = regime_result
        s = daily_stats
        m = metrics

        regime_emoji = "✅" if r.get("correct") else "❌"
        pnl_emoji = "💰" if s.get("pnl", 0) > 0 else "💸" if s.get("pnl", 0) < 0 else "➖"

        report = (
            f"📋 <b>DAILY REPORT CARD</b>\n"
            f"📅 {datetime.now().strftime('%A, %d %B %Y')}\n\n"
            f"<b>REGIME ACCURACY</b>\n"
            f"  {regime_emoji} Predicted: {r.get('predicted', 'N/A')} | Actual: {r.get('actual', 'N/A')}\n"
            f"  Move: {r.get('net_move_pct', 0)}% | Range: {r.get('range_pct', 0)}%\n\n"
            f"<b>TODAY'S PERFORMANCE</b>\n"
            f"  {pnl_emoji} P&L: ₹{s.get('pnl', 0):+,.2f}\n"
            f"  Trades: {s.get('trades', 0)} | W:{s.get('wins', 0)} L:{s.get('losses', 0)}\n"
            f"  Capital: ₹{s.get('capital_after', config.TOTAL_CAPITAL):,.2f}\n\n"
        )

        if m and m.get("total_trades", 0) > 5:
            regime_acc = self.get_regime_accuracy()
            report += (
                f"<b>ALL-TIME METRICS ({m['total_trades']} trades)</b>\n"
                f"  Win Rate: {m['win_rate']}%\n"
                f"  Profit Factor: {m['profit_factor']}\n"
                f"  Expectancy: ₹{m['expectancy']:,.2f}/trade\n"
                f"  Sharpe: {m['sharpe_ratio']} | Max DD: {m['max_drawdown_pct']}%\n"
                f"  Regime Accuracy: {regime_acc.get('accuracy', 0)}% ({regime_acc.get('total_days', 0)} days)\n"
            )

        # Health indicators
        health = []
        if m.get("win_rate", 0) >= 55: health.append("✅ Win rate healthy")
        elif m.get("win_rate", 0) >= 45: health.append("⚠️ Win rate borderline")
        else: health.append("❌ Win rate too low — review strategy")

        if m.get("profit_factor", 0) >= 1.3: health.append("✅ Profit factor good")
        elif m.get("profit_factor", 0) >= 1.0: health.append("⚠️ Profit factor thin")
        else: health.append("❌ Losing money — pause and review")

        if m.get("max_drawdown_pct", 0) < 15: health.append("✅ Drawdown controlled")
        else: health.append("❌ Drawdown too deep — reduce size")

        report += "\n<b>SYSTEM HEALTH</b>\n" + "\n".join(f"  {h}" for h in health)

        return report

    # ── Logging ──

    def _log_regime(self, result: Dict):
        exists = os.path.exists(self.regime_log_file)
        with open(self.regime_log_file, "a", newline="") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "predicted", "actual", "correct", "net_move_pct", "range_pct", "reversals"])
            w.writerow([result["date"], result["predicted"], result["actual"],
                        result["correct"], result["net_move_pct"], result["range_pct"], result["reversals"]])

    def log_equity(self, date: str, equity: float, pnl: float):
        exists = os.path.exists(self.equity_file)
        with open(self.equity_file, "a", newline="") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "equity", "daily_pnl"])
            w.writerow([date, round(equity, 2), round(pnl, 2)])
