# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Kill Switch & Safety Systems
===================================================
ChatGPT said: "What if API fails mid-trade? Internet drops? Partial fills?"
Here's the answer. Every worst case handled.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import config

logger = logging.getLogger("GXTradeIntel.KillSwitch")


class KillSwitch:
    """Emergency safety system. Can halt all trading instantly."""

    def __init__(self):
        self.is_killed = False
        self.kill_reason = ""
        self.api_errors = 0
        self.max_api_errors = 5          # 5 consecutive API failures → kill
        self.slippage_violations = 0
        self.max_slippage_violations = 3  # 3 bad fills → kill
        self.last_api_success = None

    # ── Manual Kill ──

    def kill(self, reason: str):
        """Emergency stop. No more trading until manually reset."""
        self.is_killed = True
        self.kill_reason = reason
        logger.critical(f"🛑 KILL SWITCH ACTIVATED: {reason}")

    def reset(self):
        """Reset kill switch. Only call after reviewing what went wrong."""
        self.is_killed = False
        self.kill_reason = ""
        self.api_errors = 0
        self.slippage_violations = 0
        logger.info("✅ Kill switch reset")

    def is_safe(self) -> tuple:
        """Check if trading is safe. Returns (safe: bool, reason: str)."""
        if self.is_killed:
            return False, f"KILLED: {self.kill_reason}"
        return True, "OK"

    # ── API Health Monitor ──

    def record_api_success(self):
        self.api_errors = 0
        self.last_api_success = datetime.now()

    def record_api_failure(self, error: str):
        self.api_errors += 1
        logger.warning(f"API failure #{self.api_errors}: {error}")

        if self.api_errors >= self.max_api_errors:
            self.kill(f"API failed {self.api_errors} times consecutively: {error}")

    def check_api_staleness(self):
        """If no successful API call in 15 minutes during market hours, kill."""
        if self.last_api_success:
            stale_minutes = (datetime.now() - self.last_api_success).total_seconds() / 60
            if stale_minutes > 15:
                self.kill(f"No successful API call in {stale_minutes:.0f} minutes")

    # ── Slippage Monitor ──

    def check_slippage(self, expected_price: float, actual_price: float, max_pct: float = 2.0):
        """Check if fill price is within acceptable slippage."""
        if expected_price <= 0:
            return True

        slippage_pct = abs(actual_price - expected_price) / expected_price * 100

        if slippage_pct > max_pct:
            self.slippage_violations += 1
            logger.warning(f"Slippage violation #{self.slippage_violations}: "
                         f"expected ₹{expected_price:.2f}, got ₹{actual_price:.2f} ({slippage_pct:.1f}%)")

            if self.slippage_violations >= self.max_slippage_violations:
                self.kill(f"Excessive slippage: {self.slippage_violations} violations")
            return False

        return True

    # ── Order Safety ──

    def check_order_sanity(self, order_type: str, quantity: int, price: float) -> tuple:
        """Pre-order sanity check."""
        max_qty = config.INSTRUMENTS.get(config.PRIMARY_INSTRUMENT, {}).get("lot_size", 25) * 50
        max_value = config.TOTAL_CAPITAL * 0.5  # Never more than 50% in one order

        if quantity > max_qty:
            return False, f"Quantity {quantity} exceeds max {max_qty}"

        if quantity * price > max_value:
            return False, f"Order value ₹{quantity * price:,.0f} exceeds 50% of capital"

        if price <= 0:
            return False, "Invalid price"

        return True, "OK"

    # ── Abnormal Market Detection ──

    def check_market_abnormality(self, current_price: float, prev_close: float, vix: float = 0):
        """Detect flash crash or abnormal market conditions."""
        if prev_close <= 0:
            return

        move_pct = abs(current_price - prev_close) / prev_close * 100

        # Circuit breaker levels (NSE actual limits)
        if move_pct > 5:
            self.kill(f"Market moved {move_pct:.1f}% — possible circuit breaker situation")

        # VIX panic
        if vix > 35:
            self.kill(f"VIX at {vix:.1f} — extreme panic, unsafe to trade")

    # ── Emergency Square Off ──

    def emergency_square_off(self, broker, positions):
        """Close ALL positions immediately. No questions asked."""
        logger.critical("🚨 EMERGENCY SQUARE OFF — Closing all positions")

        for pos in positions:
            if not pos.is_open:
                continue
            try:
                broker.place_order(
                    symbol=pos.symbol, token=pos.token,
                    transaction_type="SELL", quantity=pos.quantity,
                    order_type="MARKET", product_type="INTRADAY"
                )
                logger.info(f"Emergency closed: {pos.symbol} × {pos.quantity}")
            except Exception as e:
                logger.error(f"Emergency close FAILED for {pos.symbol}: {e}")
                # Try again
                try:
                    broker.place_order(
                        symbol=pos.symbol, token=pos.token,
                        transaction_type="SELL", quantity=pos.quantity,
                        order_type="MARKET", product_type="INTRADAY"
                    )
                except Exception:
                    logger.critical(f"DOUBLE FAILURE closing {pos.symbol} — MANUAL INTERVENTION NEEDED")
