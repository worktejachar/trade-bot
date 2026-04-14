# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Multi-Broker Engine
=========================================
Fixes 3 gaps:
  1. Order confirmation loop (check fill, retry)
  2. State persistence (save positions to JSON, recover after crash)
  3. Zerodha Kite Connect support (alongside Angel One)

Usage in config.py:
  BROKER = "ANGEL"    → Uses Angel One SmartAPI
  BROKER = "ZERODHA"  → Uses Zerodha Kite Connect
"""
import json
import os
import time as t_
import logging
from datetime import datetime
from typing import Optional, Dict, List

import config

logger = logging.getLogger("GXTradeIntel.MultiBroker")

STATE_FILE = f"{config.LOG_DIR}/open_positions.json"


# ═══════════════════════════════════════
# BROKER INTERFACE (common for both)
# ═══════════════════════════════════════

class BrokerBase:
    """Base class all brokers must implement."""

    def login(self) -> bool: raise NotImplementedError
    def logout(self): raise NotImplementedError
    def get_ltp(self, exchange, symbol, token) -> Optional[float]: raise NotImplementedError
    def get_historical_data(self, exchange, token, interval, days_back) -> "pd.DataFrame": raise NotImplementedError
    def place_order(self, **kwargs) -> Optional[str]: raise NotImplementedError
    def cancel_order(self, order_id) -> bool: raise NotImplementedError
    def get_order_status(self, order_id) -> Optional[str]: raise NotImplementedError
    def get_positions(self) -> List[Dict]: raise NotImplementedError
    def load_instruments(self): raise NotImplementedError
    def find_atm_option(self, symbol, spot, option_type, offset) -> Optional[Dict]: raise NotImplementedError
    def refresh_session(self) -> bool: raise NotImplementedError

    @property
    def connected(self) -> bool: return False


# ═══════════════════════════════════════
# FIX 1: ORDER CONFIRMATION LOOP
# ═══════════════════════════════════════

class OrderConfirmation:
    """Bulletproof order execution — handles volume freeze, partial fills, rejections."""

    # NSE Volume Freeze limits (orders above these get frozen)
    VOLUME_FREEZE = {
        "NIFTY": 1800,      # Max 1800 qty per order for Nifty options
        "BANKNIFTY": 900,    # Max 900 qty per order for BankNifty options
        "FINNIFTY": 1800,
        "DEFAULT": 1800,
    }

    @staticmethod
    def split_for_volume_freeze(symbol: str, total_qty: int, lot_size: int) -> list:
        """Split large orders to stay under NSE volume freeze limits."""
        # Detect instrument
        instrument = "DEFAULT"
        for key in OrderConfirmation.VOLUME_FREEZE:
            if key in symbol.upper():
                instrument = key
                break

        max_qty = OrderConfirmation.VOLUME_FREEZE[instrument]

        if total_qty <= max_qty:
            return [total_qty]

        # Split into chunks
        chunks = []
        remaining = total_qty
        while remaining > 0:
            chunk = min(remaining, max_qty)
            # Ensure chunk is multiple of lot_size
            chunk = (chunk // lot_size) * lot_size
            if chunk <= 0:
                break
            chunks.append(chunk)
            remaining -= chunk

        logger.info(f"📦 Volume freeze split: {total_qty} → {chunks} (limit: {max_qty})")
        return chunks

    @staticmethod
    def confirm_order(broker: BrokerBase, order_id: str, max_wait_sec: int = 30, check_interval: int = 2) -> Dict:
        """Wait for order to fill. Handles all states including volume freeze."""
        if not order_id or order_id.startswith("PAPER"):
            return {"status": "FILLED", "order_id": order_id, "fill_price": 0, "filled_qty": 0}

        start = datetime.now()
        backoff = check_interval

        while (datetime.now() - start).total_seconds() < max_wait_sec:
            try:
                status = broker.get_order_status(order_id)

                if status == "complete":
                    # Get actual fill price
                    fill_price = OrderConfirmation._get_fill_price(broker, order_id)
                    fill_qty = OrderConfirmation._get_fill_qty(broker, order_id)
                    logger.info(f"✅ Order {order_id} FILLED @ ₹{fill_price} qty={fill_qty}")
                    return {"status": "FILLED", "order_id": order_id,
                            "fill_price": fill_price, "filled_qty": fill_qty}

                elif status == "rejected":
                    reject_reason = OrderConfirmation._get_reject_reason(broker, order_id)
                    logger.error(f"❌ Order {order_id} REJECTED: {reject_reason}")

                    # Volume freeze rejection → split and retry
                    if "freeze" in reject_reason.lower() or "quantity" in reject_reason.lower():
                        return {"status": "VOLUME_FREEZE", "order_id": order_id, "reason": reject_reason}

                    return {"status": "REJECTED", "order_id": order_id, "reason": reject_reason}

                elif status == "cancelled":
                    return {"status": "CANCELLED", "order_id": order_id}

                elif status in ("partially_filled", "partial"):
                    filled_qty = OrderConfirmation._get_fill_qty(broker, order_id)
                    fill_price = OrderConfirmation._get_fill_price(broker, order_id)
                    if filled_qty > 0:
                        logger.warning(f"⚠️ Partial fill: {filled_qty} filled. Keeping partial position.")
                        return {"status": "FILLED", "order_id": order_id,
                                "fill_price": fill_price, "filled_qty": filled_qty, "partial": True}

                # Exponential backoff
                t_.sleep(backoff)
                backoff = min(backoff * 1.5, 5)  # Cap at 5 seconds

            except Exception as e:
                logger.warning(f"Order check error: {e}")
                t_.sleep(backoff)

        # Timeout — cancel and report
        logger.warning(f"⏰ Order {order_id} not filled in {max_wait_sec}s — cancelling")
        broker.cancel_order(order_id)
        return {"status": "TIMEOUT", "order_id": order_id}

    @staticmethod
    def place_with_retry(broker: BrokerBase, max_retries: int = 3, **order_params) -> Optional[Dict]:
        """Bulletproof order placement: retry + volume freeze split + fill confirmation."""
        symbol = order_params.get("symbol", "")
        quantity = order_params.get("quantity", 0)
        lot_size = 25  # Default Nifty

        # Check volume freeze BEFORE placing
        chunks = OrderConfirmation.split_for_volume_freeze(symbol, quantity, lot_size)

        all_fills = []
        for chunk_qty in chunks:
            chunk_params = {**order_params, "quantity": chunk_qty}

            for attempt in range(max_retries):
                try:
                    order_id = broker.place_order(**chunk_params)
                    if not order_id:
                        logger.warning(f"Order attempt {attempt+1} returned no ID")
                        t_.sleep(2)
                        continue

                    result = OrderConfirmation.confirm_order(broker, order_id)

                    if result["status"] == "FILLED":
                        all_fills.append(result)
                        break

                    elif result["status"] == "VOLUME_FREEZE":
                        # Split further
                        sub_chunks = OrderConfirmation.split_for_volume_freeze(
                            symbol, chunk_qty, lot_size)
                        if len(sub_chunks) > 1:
                            logger.info(f"Re-splitting frozen order: {chunk_qty} → {sub_chunks}")
                            for sc in sub_chunks:
                                sc_params = {**order_params, "quantity": sc}
                                sc_id = broker.place_order(**sc_params)
                                if sc_id:
                                    sc_result = OrderConfirmation.confirm_order(broker, sc_id)
                                    if sc_result["status"] == "FILLED":
                                        all_fills.append(sc_result)
                        break

                    elif result["status"] == "REJECTED":
                        return result  # Don't retry true rejections

                    elif result["status"] == "TIMEOUT":
                        logger.warning(f"Timeout attempt {attempt+1}, retrying...")
                        t_.sleep(3)
                        continue

                except Exception as e:
                    logger.error(f"Order attempt {attempt+1} error: {e}")
                    t_.sleep(3)

        if all_fills:
            total_qty = sum(f.get("filled_qty", 0) for f in all_fills)
            avg_price = sum(f.get("fill_price", 0) for f in all_fills) / len(all_fills) if all_fills else 0
            return {"status": "FILLED", "order_id": all_fills[0]["order_id"],
                    "fill_price": avg_price, "filled_qty": total_qty, "chunks": len(all_fills)}

        logger.error(f"All order attempts failed for {symbol}")
        return {"status": "FAILED", "order_id": None}

    @staticmethod
    def _get_fill_price(broker, order_id) -> float:
        try:
            if hasattr(broker, 'kite') and broker.kite:
                orders = broker.kite.orders()
                for o in orders:
                    if str(o["order_id"]) == str(order_id):
                        return float(o.get("average_price", 0))
            elif hasattr(broker, 'obj') and broker.obj:
                order_book = broker.obj.orderBook()
                if order_book and order_book.get("data"):
                    for o in order_book["data"]:
                        if o.get("orderid") == str(order_id):
                            return float(o.get("averageprice", 0))
        except Exception:
            pass
        return 0

    @staticmethod
    def _get_fill_qty(broker, order_id) -> int:
        try:
            if hasattr(broker, 'kite') and broker.kite:
                orders = broker.kite.orders()
                for o in orders:
                    if str(o["order_id"]) == str(order_id):
                        return int(o.get("filled_quantity", 0))
            elif hasattr(broker, 'obj') and broker.obj:
                order_book = broker.obj.orderBook()
                if order_book and order_book.get("data"):
                    for o in order_book["data"]:
                        if o.get("orderid") == str(order_id):
                            return int(o.get("filledshares", 0))
        except Exception:
            pass
        return 0

    @staticmethod
    def _get_reject_reason(broker, order_id) -> str:
        try:
            if hasattr(broker, 'kite') and broker.kite:
                orders = broker.kite.orders()
                for o in orders:
                    if str(o["order_id"]) == str(order_id):
                        return o.get("status_message", "Unknown")
            elif hasattr(broker, 'obj') and broker.obj:
                order_book = broker.obj.orderBook()
                if order_book and order_book.get("data"):
                    for o in order_book["data"]:
                        if o.get("orderid") == str(order_id):
                            return o.get("text", "Unknown")
        except Exception:
            pass
        return "Unknown"


# ═══════════════════════════════════════
# FIX 2: STATE PERSISTENCE
# ═══════════════════════════════════════

class StatePersistence:
    """Save/load bot state to survive crashes."""

    @staticmethod
    def save_positions(positions: list):
        """Save open positions to JSON file."""
        data = []
        for p in positions:
            if not p.is_open:
                continue
            data.append({
                "symbol": p.symbol, "token": p.token, "direction": p.direction,
                "entry_price": p.entry_price, "quantity": p.quantity,
                "stop_loss": p.stop_loss, "target_1": p.target_1, "target_2": p.target_2,
                "order_id": p.order_id, "entry_time": p.entry_time.isoformat(),
                "highest_premium": p.highest_premium, "trailing_active": p.trailing_active,
            })

        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"positions": data, "saved_at": datetime.now().isoformat()}, f, indent=2)

        if data:
            logger.info(f"💾 Saved {len(data)} open position(s) to state file")

    @staticmethod
    def load_positions() -> list:
        """Load positions from JSON after crash/restart."""
        if not os.path.exists(STATE_FILE):
            return []

        try:
            with open(STATE_FILE) as f:
                data = json.load(f)

            positions = data.get("positions", [])
            saved_at = data.get("saved_at", "")

            if positions:
                logger.info(f"🔄 Recovered {len(positions)} position(s) from {saved_at}")
            return positions

        except Exception as e:
            logger.error(f"State load error: {e}")
            return []

    @staticmethod
    def clear_state():
        """Clear state file after clean exit."""
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

    @staticmethod
    def save_bot_state(regime: str, engine: str, daily_pnl: float, trades: int):
        """Save broader bot state for recovery."""
        state = {
            "regime": regime, "engine": engine,
            "daily_pnl": daily_pnl, "trades_today": trades,
            "saved_at": datetime.now().isoformat(),
        }
        state_path = f"{config.LOG_DIR}/bot_state.json"
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)


# ═══════════════════════════════════════
# FIX 3: ZERODHA KITE CONNECT BROKER
# ═══════════════════════════════════════

class ZerodhaBroker(BrokerBase):
    """Zerodha Kite Connect integration."""

    def __init__(self):
        self.kite = None
        self._connected = False
        self.instrument_df = None

        try:
            from kiteconnect import KiteConnect
            self.KiteConnect = KiteConnect
            self.AVAILABLE = True
        except ImportError:
            self.AVAILABLE = False
            logger.warning("⚠️ kiteconnect not installed. Run: pip install kiteconnect")

    @property
    def connected(self): return self._connected

    def login(self) -> bool:
        """Login to Zerodha.
        NOTE: Zerodha requires browser-based login for request_token.
        For full automation, use selenium or manual daily token paste.
        """
        if not self.AVAILABLE:
            return False

        try:
            self.kite = self.KiteConnect(api_key=config.ZERODHA_API_KEY)

            # Check if we have a saved access token from today
            token_file = f"{config.LOG_DIR}/zerodha_token.json"
            if os.path.exists(token_file):
                with open(token_file) as f:
                    token_data = json.load(f)
                if token_data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                    self.kite.set_access_token(token_data["access_token"])
                    self._connected = True
                    logger.info(f"✅ Zerodha: Using saved token from today")
                    return True

            # Need fresh login — generate login URL
            login_url = self.kite.login_url()
            logger.info(f"🔑 Zerodha login required. Open this URL and paste the request_token:")
            logger.info(f"   {login_url}")

            # In production, use selenium or manual paste
            # For now, check if request_token is in env
            request_token = os.environ.get("ZERODHA_REQUEST_TOKEN", "")
            if not request_token:
                logger.warning("Set ZERODHA_REQUEST_TOKEN env variable after browser login")
                return False

            data = self.kite.generate_session(request_token, api_secret=config.ZERODHA_API_SECRET)
            self.kite.set_access_token(data["access_token"])

            # Save token for today
            with open(token_file, "w") as f:
                json.dump({
                    "access_token": data["access_token"],
                    "date": datetime.now().strftime("%Y-%m-%d"),
                }, f)

            self._connected = True
            profile = self.kite.profile()
            logger.info(f"✅ Zerodha: Logged in as {profile.get('user_name', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"Zerodha login error: {e}")
            return False

    def logout(self):
        try:
            if self.kite:
                self.kite.invalidate_access_token()
            self._connected = False
        except Exception:
            pass

    def get_ltp(self, exchange, symbol, token) -> Optional[float]:
        try:
            key = f"{exchange}:{symbol}"
            data = self.kite.quote(key)
            return data[key]["last_price"]
        except Exception as e:
            logger.error(f"Zerodha LTP error: {e}")
            return None

    def get_historical_data(self, exchange, token, interval="5minute", days_back=5):
        import pandas as pd
        try:
            to_date = datetime.now()
            from_date = to_date - __import__("datetime").timedelta(days=days_back)
            data = self.kite.historical_data(
                int(token), from_date, to_date, interval, continuous=False, oi=False
            )
            df = pd.DataFrame(data)
            if not df.empty:
                df = df.rename(columns={"date": "timestamp"})
            return df
        except Exception as e:
            logger.error(f"Zerodha historical error: {e}")
            return pd.DataFrame()

    def place_order(self, symbol, token, transaction_type, quantity,
                    order_type="MARKET", product_type="INTRADAY", **kwargs) -> Optional[str]:
        if config.PAPER_TRADE:
            oid = f"PAPER_Z_{datetime.now():%H%M%S}_{symbol[:8]}"
            logger.info(f"📝 PAPER (Zerodha): {transaction_type} {quantity}x {symbol} | ID: {oid}")
            return oid

        try:
            product = self.kite.PRODUCT_MIS if product_type == "INTRADAY" else self.kite.PRODUCT_CNC
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=self.kite.EXCHANGE_NFO,
                tradingsymbol=symbol,
                transaction_type=self.kite.TRANSACTION_TYPE_BUY if transaction_type == "BUY" else self.kite.TRANSACTION_TYPE_SELL,
                quantity=quantity,
                product=product,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            logger.info(f"✅ Zerodha order: {transaction_type} {quantity}x {symbol} | ID: {order_id}")
            return str(order_id)
        except Exception as e:
            logger.error(f"Zerodha order error: {e}")
            return None

    def get_order_status(self, order_id) -> Optional[str]:
        try:
            orders = self.kite.orders()
            for o in orders:
                if str(o["order_id"]) == str(order_id):
                    return o["status"].lower()
        except Exception:
            pass
        return None

    def cancel_order(self, order_id) -> bool:
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception:
            return False

    def get_positions(self) -> List[Dict]:
        try:
            pos = self.kite.positions()
            return pos.get("net", [])
        except Exception:
            return []

    def load_instruments(self):
        import pandas as pd
        try:
            instruments = self.kite.instruments("NFO")
            self.instrument_df = pd.DataFrame(instruments)
            logger.info(f"📦 Zerodha: Loaded {len(self.instrument_df)} instruments")
        except Exception as e:
            logger.error(f"Zerodha instruments error: {e}")

    def find_atm_option(self, symbol, spot_price, option_type="CE", offset=0):
        if self.instrument_df is None:
            self.load_instruments()
        if self.instrument_df is None or self.instrument_df.empty:
            return None

        df = self.instrument_df
        opts = df[(df["name"] == symbol) & (df["instrument_type"] == option_type) &
                  (df["segment"] == "NFO-OPT")].copy()

        if opts.empty:
            return None

        today = __import__("pandas").Timestamp.now().normalize()
        future = opts[opts["expiry"] >= today].sort_values("expiry")
        if future.empty:
            return None

        nearest_expiry = future["expiry"].iloc[0]
        opts = opts[opts["expiry"] == nearest_expiry]

        opts["distance"] = abs(opts["strike"] - spot_price)
        opts = opts.sort_values("distance")

        if opts.empty:
            return None

        contract = opts.iloc[min(offset, len(opts)-1)]
        return {
            "symbol": contract["tradingsymbol"],
            "token": str(contract["instrument_token"]),
            "strike": contract["strike"],
            "lot_size": int(contract["lot_size"]),
            "exchange": "NFO",
            "option_type": option_type,
        }

    def refresh_session(self) -> bool:
        return self._connected


# ═══════════════════════════════════════
# BROKER FACTORY
# ═══════════════════════════════════════

def get_broker() -> BrokerBase:
    """Get the configured broker instance."""
    broker_name = getattr(config, "BROKER", "ANGEL").upper()

    if broker_name == "ZERODHA":
        logger.info("🔧 Using Zerodha Kite Connect")
        return ZerodhaBroker()
    else:
        logger.info("🔧 Using Angel One SmartAPI")
        from broker import AngelOneBroker
        return AngelOneBroker()
