# -*- coding: utf-8 -*-
"""
GX TradeIntel - Broker Connector
=================================
Angel One SmartAPI integration for:
- Authentication (TOTP-based auto-login)
- Live market data (LTP, WebSocket)
- Historical OHLCV data
- Order placement & management
- Option chain fetching
"""

import time as time_mod
import logging
import json
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

import pyotp
import pandas as pd
import requests

try:
    from SmartApi import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    SMARTAPI_AVAILABLE = True
except ImportError:
    SMARTAPI_AVAILABLE = False
    print("⚠️  smartapi-python not installed. Run: pip install smartapi-python pyotp")

import config

logger = logging.getLogger("GXTradeIntel.Broker")


class AngelOneBroker:
    """Angel One SmartAPI wrapper for GX TradeIntel."""

    def __init__(self):
        self.api = None
        self.auth_token = None
        self.refresh_token = None
        self.feed_token = None
        self.ws = None
        self.connected = False
        self.ltp_cache: Dict[str, float] = {}
        self.instrument_df: Optional[pd.DataFrame] = None
        self._ws_thread = None

    # ── Authentication ──────────────────────────

    def login(self) -> bool:
        """Auto-login using TOTP."""
        if not SMARTAPI_AVAILABLE:
            logger.error("SmartAPI not installed")
            return False

        try:
            self.api = SmartConnect(api_key=config.ANGEL_API_KEY)
            totp = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()

            data = self.api.generateSession(
                config.ANGEL_CLIENT_ID,
                config.ANGEL_PASSWORD,
                totp
            )

            if not data or data.get("status") is False:
                logger.error(f"Login failed: {data}")
                return False

            self.auth_token = data["data"]["jwtToken"]
            self.refresh_token = data["data"]["refreshToken"]
            self.feed_token = self.api.getfeedToken()
            self.connected = True

            profile = self.api.getProfile(self.refresh_token)
            client_name = profile.get("data", {}).get("name", "Unknown")

            logger.info(f"✅ Logged in as: {client_name} ({config.ANGEL_CLIENT_ID})")
            return True

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def refresh_session(self) -> bool:
        """Refresh auth token."""
        try:
            self.api.generateToken(self.refresh_token)
            logger.info("🔄 Session refreshed")
            return True
        except Exception as e:
            logger.warning(f"Token refresh failed, re-logging: {e}")
            return self.login()

    # ── Instrument Data ─────────────────────────

    def load_instruments(self) -> pd.DataFrame:
        """Load full instrument master from Angel One."""
        try:
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            resp = requests.get(url, timeout=30)
            data = resp.json()
            self.instrument_df = pd.DataFrame(data)
            self.instrument_df["expiry"] = pd.to_datetime(
                self.instrument_df["expiry"], errors="coerce"
            )
            self.instrument_df["strike"] = pd.to_numeric(
                self.instrument_df["strike"], errors="coerce"
            )
            logger.info(f"📦 Loaded {len(self.instrument_df)} instruments")
            return self.instrument_df
        except Exception as e:
            logger.error(f"Instrument load error: {e}")
            return pd.DataFrame()

    def get_option_contracts(
        self, symbol: str = "NIFTY", expiry_offset: int = 0
    ) -> pd.DataFrame:
        """Get option contracts for nearest expiry."""
        if self.instrument_df is None:
            self.load_instruments()

        df = self.instrument_df
        opts = df[
            (df["name"] == symbol)
            & (df["instrumenttype"].isin(["OPTIDX"]))
            & (df["exch_seg"] == "NFO")
        ].copy()

        if opts.empty:
            logger.warning(f"No options found for {symbol}")
            return pd.DataFrame()

        # Get nearest expiry
        today = pd.Timestamp.now().normalize()
        future_expiries = sorted(opts["expiry"].dropna().unique())
        future_expiries = [e for e in future_expiries if e >= today]

        if not future_expiries:
            logger.warning("No future expiries found")
            return pd.DataFrame()

        target_expiry = future_expiries[min(expiry_offset, len(future_expiries) - 1)]
        opts = opts[opts["expiry"] == target_expiry]

        logger.info(f"📋 Found {len(opts)} {symbol} options for expiry {target_expiry.date()}")
        return opts

    def find_atm_option(
        self, symbol: str, spot_price: float, option_type: str = "CE", offset: int = 0
    ) -> Optional[Dict]:
        """Find ATM (or near ATM) option contract."""
        opts = self.get_option_contracts(symbol)
        if opts.empty:
            return None

        # Filter by option type
        type_filter = opts["symbol"].str.endswith(option_type)
        filtered = opts[type_filter].copy()

        # Find nearest strike to spot price
        filtered["strike_val"] = filtered["strike"] / 100
        filtered["distance"] = abs(filtered["strike_val"] - spot_price)
        filtered = filtered.sort_values("distance")

        if filtered.empty:
            return None

        # Apply offset (0 = ATM, 1 = next OTM, -1 = next ITM)
        idx = max(0, min(offset, len(filtered) - 1))
        contract = filtered.iloc[idx]

        return {
            "symbol": contract["symbol"],
            "token": contract["token"],
            "strike": contract["strike_val"],
            "expiry": contract["expiry"],
            "lot_size": int(contract["lotsize"]),
            "exchange": "NFO",
            "option_type": option_type,
        }

    # ── Market Data ─────────────────────────────

    def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        """Get Last Traded Price."""
        try:
            data = self.api.ltpData(exchange, symbol, token)
            if data and data.get("data"):
                ltp = data["data"]["ltp"]
                self.ltp_cache[f"{exchange}:{token}"] = ltp
                return ltp
        except Exception as e:
            logger.error(f"LTP error for {symbol}: {e}")
        return self.ltp_cache.get(f"{exchange}:{token}")

    def get_nifty_ltp(self) -> Optional[float]:
        """Get current Nifty 50 spot price."""
        return self.get_ltp("NSE", "Nifty 50", "99926000")

    def get_banknifty_ltp(self) -> Optional[float]:
        """Get current Bank Nifty spot price."""
        return self.get_ltp("NSE", "Nifty Bank", "99926009")

    def get_historical_data(
        self,
        exchange: str,
        token: str,
        interval: str = "FIVE_MINUTE",
        days_back: int = 5,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV candles."""
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days_back)

            params = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date.strftime("%Y-%m-%d 09:15"),
                "todate": to_date.strftime("%Y-%m-%d 15:30"),
            }

            data = self.api.getCandleData(params)

            if not data or not data.get("data"):
                logger.warning(f"No historical data for token {token}")
                return pd.DataFrame()

            df = pd.DataFrame(
                data["data"],
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)

            logger.info(f"📊 Fetched {len(df)} candles for token {token}")
            return df

        except Exception as e:
            logger.error(f"Historical data error: {e}")
            return pd.DataFrame()

    # ── Order Management ────────────────────────

    def place_order(
        self,
        symbol: str,
        token: str,
        transaction_type: str,  # "BUY" or "SELL"
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0,
        trigger_price: float = 0,
        variety: str = "NORMAL",
        product_type: str = "INTRADAY",
    ) -> Optional[str]:
        """Place an order on Angel One."""

        if config.PAPER_TRADE:
            order_id = f"PAPER_{datetime.now().strftime('%H%M%S')}_{symbol[:6]}"
            logger.info(
                f"📝 PAPER ORDER: {transaction_type} {quantity}x {symbol} "
                f"@ {'MARKET' if order_type == 'MARKET' else price} | ID: {order_id}"
            )
            return order_id

        try:
            order_params = {
                "variety": variety,
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": transaction_type,
                "exchange": "NFO",
                "ordertype": order_type,
                "producttype": product_type,
                "duration": "DAY",
                "quantity": quantity,
            }

            if order_type == "LIMIT":
                order_params["price"] = price
            if order_type == "STOPLOSS_LIMIT":
                order_params["triggerprice"] = trigger_price
                order_params["price"] = price

            result = self.api.placeOrder(order_params)

            if result:
                logger.info(f"✅ ORDER PLACED: {transaction_type} {quantity}x {symbol} | ID: {result}")
                return result
            else:
                logger.error(f"Order placement failed for {symbol}")
                return None

        except Exception as e:
            logger.error(f"Order error: {e}")
            return None

    def cancel_order(self, order_id: str, variety: str = "NORMAL") -> bool:
        """Cancel an open order."""
        if config.PAPER_TRADE:
            logger.info(f"📝 PAPER CANCEL: {order_id}")
            return True

        try:
            result = self.api.cancelOrder(order_id, variety)
            logger.info(f"❌ Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False

    def get_positions(self) -> List[Dict]:
        """Get current open positions."""
        if config.PAPER_TRADE:
            return []

        try:
            positions = self.api.position()
            if positions and positions.get("data"):
                return positions["data"]
            return []
        except Exception as e:
            logger.error(f"Positions error: {e}")
            return []

    def get_order_book(self) -> List[Dict]:
        """Get today's order book."""
        if config.PAPER_TRADE:
            return []

        try:
            orders = self.api.orderBook()
            if orders and orders.get("data"):
                return orders["data"]
            return []
        except Exception as e:
            logger.error(f"Order book error: {e}")
            return []

    # ── WebSocket (Real-time) ───────────────────

    def start_websocket(self, tokens: List[Dict], on_tick=None):
        """Start WebSocket for real-time price feed.

        tokens format: [{"exchangeType": 1, "tokens": ["26000", "26009"]}]
        exchangeType: 1=NSE, 2=NFO, 3=BSE
        """
        if not SMARTAPI_AVAILABLE:
            return

        def _on_data(wsapp, msg):
            if on_tick:
                on_tick(msg)

        def _on_open(wsapp):
            logger.info("🔌 WebSocket connected")
            sws.subscribe("abc123", 1, tokens)  # mode 1 = LTP

        def _on_error(wsapp, error):
            logger.error(f"WebSocket error: {error}")

        def _on_close(wsapp):
            logger.info("🔌 WebSocket disconnected")

        try:
            sws = SmartWebSocketV2(
                self.auth_token,
                config.ANGEL_API_KEY,
                config.ANGEL_CLIENT_ID,
                self.feed_token,
            )
            sws.on_open = _on_open
            sws.on_data = _on_data
            sws.on_error = _on_error
            sws.on_close = _on_close

            self._ws_thread = threading.Thread(target=sws.connect, daemon=True)
            self._ws_thread.start()
            self.ws = sws

        except Exception as e:
            logger.error(f"WebSocket start error: {e}")

    # ── Cleanup ─────────────────────────────────

    def logout(self):
        """Clean disconnect."""
        try:
            if self.ws:
                self.ws.close_connection()
            if self.api:
                self.api.terminateSession(config.ANGEL_CLIENT_ID)
            self.connected = False
            logger.info("👋 Logged out from Angel One")
        except Exception as e:
            logger.error(f"Logout error: {e}")
