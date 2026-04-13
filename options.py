# -*- coding: utf-8 -*-
"""
GX TradeIntel v4 — Options Intelligence
==========================================
Source: options-mastery-india (full skill)
Handles: OI analysis, PCR, Max Pain, strike selection, theta/day filters
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List

import pandas as pd
import numpy as np

import config

logger = logging.getLogger("GXTradeIntel.Options")


class OptionsIntelligence:
    """Everything about options — from the options-mastery-india skill."""

    # ── Day-of-Week Filter [options-mastery §7] ──

    @staticmethod
    def is_good_trading_day() -> tuple:
        """Check if today is a good day for option buying."""
        day_name = datetime.now().strftime("%A")

        if day_name in config.OPTIONS.get("avoid_days", ["Thursday"]):
            return False, f"{day_name} is expiry day — too risky for ₹10K (extreme gamma)"

        if day_name in config.OPTIONS.get("best_days", []):
            return True, f"{day_name} — good for option buying"

        return True, f"{day_name} — normal trading day"

    # ── Theta Awareness [options-mastery §2] ──

    @staticmethod
    def theta_risk_level() -> dict:
        """Estimate theta risk based on day of week."""
        day = datetime.now().weekday()  # 0=Mon, 4=Fri
        # For weekly expiry (Thursday):
        days_to_expiry = (3 - day) % 7  # Days until Thursday
        if days_to_expiry == 0:
            days_to_expiry = 7  # If Thursday, next week

        decay_map = {
            5: {"daily_decay": "₹3-5", "premium_remaining": "90-95%", "risk": "LOW"},
            4: {"daily_decay": "₹5-8", "premium_remaining": "80-88%", "risk": "LOW"},
            3: {"daily_decay": "₹8-15", "premium_remaining": "65-78%", "risk": "MEDIUM"},
            2: {"daily_decay": "₹15-30", "premium_remaining": "40-60%", "risk": "HIGH"},
            1: {"daily_decay": "₹30-50+", "premium_remaining": "10-30%", "risk": "EXTREME"},
        }
        return decay_map.get(min(days_to_expiry, 5), decay_map[5])

    # ── Strike Selection [options-mastery §4] ──

    @staticmethod
    def select_strike(spot_price: float, direction: str, instrument: str = "NIFTY") -> dict:
        """Select optimal strike — scales with ANY capital.

        Small capital (₹10K-25K): 1 lot ATM, strict premium limits
        Medium capital (₹25K-1L): 1-3 lots, can go slightly ITM
        Large capital (₹1L+): Multiple lots, wider strike range
        """
        inst = config.INSTRUMENTS.get(instrument, {})
        lot_size = inst.get("lot_size", 25)
        strike_gap = inst.get("strike_gap", 50)
        max_cost = config.MAX_CAPITAL_PER_TRADE

        atm = round(spot_price / strike_gap) * strike_gap

        if direction == "BULLISH":
            opt_type = "CE"
            strikes = [atm, atm - strike_gap]
        else:
            opt_type = "PE"
            strikes = [atm, atm + strike_gap]

        # Dynamic premium limits based on capital
        min_premium = 30 if config.TOTAL_CAPITAL < 25000 else 20
        max_premium = max_cost / lot_size  # Whatever capital allows

        for strike in strikes:
            est_premium = OptionsIntelligence._estimate_premium(spot_price, strike, opt_type)
            total_cost_1lot = est_premium * lot_size

            if total_cost_1lot <= max_cost and est_premium >= min_premium:
                # Calculate how many lots we can afford
                affordable_lots = max(1, int(max_cost / total_cost_1lot))

                return {
                    "strike": int(strike),
                    "option_type": opt_type,
                    "est_premium": round(est_premium, 2),
                    "total_cost_1lot": round(total_cost_1lot, 2),
                    "recommended_lots": affordable_lots,
                    "total_quantity": affordable_lots * lot_size,
                    "total_cost": round(total_cost_1lot * affordable_lots, 2),
                    "lot_size": lot_size,
                    "delta_est": 0.50 if strike == atm else 0.60,
                }

        return {"strike": int(atm), "option_type": opt_type, "est_premium": 0,
                "total_cost": 0, "lot_size": lot_size, "delta_est": 0.50}

    @staticmethod
    def _estimate_premium(spot, strike, opt_type):
        intrinsic = max(0, spot - strike) if opt_type == "CE" else max(0, strike - spot)
        time_value = spot * 0.005  # ~0.5% for weekly ATM
        return intrinsic + time_value

    # ── PCR Analysis [options-mastery §3] ──

    @staticmethod
    def analyze_pcr(call_oi_total: float, put_oi_total: float) -> dict:
        """Interpret Put-Call Ratio for direction bias."""
        if call_oi_total == 0:
            return {"pcr": 0, "bias": "NEUTRAL", "strength": "NONE"}

        pcr = put_oi_total / call_oi_total
        thresholds = config.OPTIONS

        if pcr > thresholds["pcr_extreme_bull"]:
            bias, strength = "BULLISH", "EXTREME (contrarian — panic put buying = bottom)"
        elif pcr > thresholds["pcr_bullish_above"]:
            bias, strength = "BULLISH", "STRONG (put writers confident)"
        elif pcr < thresholds["pcr_extreme_bear"]:
            bias, strength = "BEARISH", "EXTREME (contrarian — euphoria = top)"
        elif pcr < thresholds["pcr_bearish_below"]:
            bias, strength = "BEARISH", "STRONG (call writers confident)"
        else:
            bias, strength = "NEUTRAL", "BALANCED"

        return {"pcr": round(pcr, 2), "bias": bias, "strength": strength}

    # ── OI-Based Levels [options-mastery §3] ──

    @staticmethod
    def oi_support_resistance(option_chain: pd.DataFrame) -> dict:
        """Find support/resistance from option chain OI data."""
        if option_chain.empty:
            return {"support": 0, "resistance": 0, "max_pain": 0, "pcr_data": {}}

        calls = option_chain[option_chain["symbol"].str.endswith("CE")]
        puts = option_chain[option_chain["symbol"].str.endswith("PE")]

        resistance = 0
        support = 0
        if not calls.empty and "oi" in calls.columns:
            resistance = calls.loc[calls["oi"].idxmax()]["strike"] if calls["oi"].max() > 0 else 0
        if not puts.empty and "oi" in puts.columns:
            support = puts.loc[puts["oi"].idxmax()]["strike"] if puts["oi"].max() > 0 else 0

        # Max Pain: strike where total OI of both CE and PE is highest
        max_pain = 0
        if not calls.empty and not puts.empty:
            merged = calls.merge(puts, on="strike", suffixes=("_ce", "_pe"))
            if "oi_ce" in merged.columns and "oi_pe" in merged.columns:
                merged["total_oi"] = merged["oi_ce"] + merged["oi_pe"]
                max_pain = merged.loc[merged["total_oi"].idxmax()]["strike"]

        # PCR
        total_call_oi = calls["oi"].sum() if "oi" in calls.columns else 0
        total_put_oi = puts["oi"].sum() if "oi" in puts.columns else 0
        pcr_data = OptionsIntelligence.analyze_pcr(total_call_oi, total_put_oi)

        return {
            "resistance": resistance,
            "support": support,
            "max_pain": max_pain,
            "pcr_data": pcr_data,
        }

    # ── Premium Validation [options-mastery §4] ──

    @staticmethod
    def validate_option(premium: float, oi: float = 0, bid_ask_spread: float = 0) -> tuple:
        """Check if an option contract meets quality criteria."""
        reasons = []

        if premium < config.OPTIONS["min_premium"]:
            reasons.append(f"Premium too low (₹{premium} < ₹{config.OPTIONS['min_premium']})")
        if premium > config.OPTIONS["max_premium"]:
            reasons.append(f"Premium too high (₹{premium} > ₹{config.OPTIONS['max_premium']})")
        if oi > 0 and oi < config.OPTIONS["min_oi"]:
            reasons.append(f"OI too low ({oi:,.0f} < {config.OPTIONS['min_oi']:,.0f})")
        if bid_ask_spread > config.OPTIONS["max_bid_ask_spread"]:
            reasons.append(f"Spread too wide (₹{bid_ask_spread} > ₹{config.OPTIONS['max_bid_ask_spread']})")

        if reasons:
            return False, reasons
        return True, ["Option meets all quality criteria"]

    # ── Trade Cost Calculator [backtesting-performance §1] ──

    @staticmethod
    def calculate_trade_cost(entry_premium: float, exit_premium: float, quantity: int) -> dict:
        """Calculate realistic all-in cost for a round trip."""
        bc = config.BACKTEST
        turnover = (entry_premium + exit_premium) * quantity
        brokerage = bc["brokerage_per_order"] * 2
        stt = exit_premium * quantity * (bc["stt_sell_pct"] / 100)
        exchange = turnover * (bc["exchange_txn_pct"] / 100)
        gst = brokerage * (bc["gst_on_brokerage_pct"] / 100)
        stamp = entry_premium * quantity * (bc["stamp_duty_buy_pct"] / 100)
        slippage = bc["slippage_per_unit"] * quantity * 2

        total = brokerage + stt + exchange + gst + stamp + slippage
        breakeven_move = total / quantity if quantity > 0 else 0

        return {
            "total_cost": round(total, 2),
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "gst": round(gst, 2),
            "slippage": round(slippage, 2),
            "breakeven_move_per_unit": round(breakeven_move, 2),
        }
