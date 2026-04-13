# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Live Data Feeds
=====================================
Fills gaps 1, 2, 3 from ChatGPT criticism:
  Gap 1: FII/DII live data → MoneyControl scraper + yfinance
  Gap 2: India VIX live → yfinance ^INDIAVIX
  Gap 3: Option Chain OI → NSE website scraper
"""
import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List

import requests
import pandas as pd
import numpy as np

logger = logging.getLogger("GXTradeIntel.LiveFeeds")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ═══════════════════════════════════════
# GAP 1: FII/DII LIVE DATA
# ═══════════════════════════════════════

class FIIDIIFetcher:
    """Fetch FII/DII daily activity data."""

    @staticmethod
    def fetch_from_moneycontrol() -> Dict:
        """Scrape FII/DII data from MoneyControl."""
        try:
            url = "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/data.json"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Parse latest entry
                if data and isinstance(data, list) and len(data) > 0:
                    latest = data[0]
                    return {
                        "date": latest.get("date", ""),
                        "fii_buy": float(latest.get("fii_buy", 0)),
                        "fii_sell": float(latest.get("fii_sell", 0)),
                        "fii_net": float(latest.get("fii_net", 0)),
                        "dii_buy": float(latest.get("dii_buy", 0)),
                        "dii_sell": float(latest.get("dii_sell", 0)),
                        "dii_net": float(latest.get("dii_net", 0)),
                        "source": "MoneyControl",
                    }
        except Exception as e:
            logger.warning(f"MoneyControl FII/DII fetch failed: {e}")

        return FIIDIIFetcher._fallback_nse()

    @staticmethod
    def _fallback_nse() -> Dict:
        """Fallback: Try NSE India website."""
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            # Hit main page first for cookies
            session.get("https://www.nseindia.com", timeout=10)

            url = "https://www.nseindia.com/api/fiidiiTradeReact"
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                fii_data = data.get("data", [])
                if fii_data:
                    fii = next((d for d in fii_data if d.get("category") == "FII/FPI *"), {})
                    dii = next((d for d in fii_data if d.get("category") == "DII **"), {})
                    return {
                        "date": data.get("date", ""),
                        "fii_buy": float(fii.get("buyValue", 0)),
                        "fii_sell": float(fii.get("sellValue", 0)),
                        "fii_net": float(fii.get("netValue", 0)),
                        "dii_buy": float(dii.get("buyValue", 0)),
                        "dii_sell": float(dii.get("sellValue", 0)),
                        "dii_net": float(dii.get("netValue", 0)),
                        "source": "NSE",
                    }
        except Exception as e:
            logger.warning(f"NSE FII/DII fetch failed: {e}")

        return {"fii_net": 0, "dii_net": 0, "source": "UNAVAILABLE"}

    @staticmethod
    def fetch() -> Dict:
        """Main entry: try all sources."""
        data = FIIDIIFetcher.fetch_from_moneycontrol()
        if data.get("source") == "UNAVAILABLE":
            data = FIIDIIFetcher._fallback_nse()
        logger.info(f"📊 FII: ₹{data.get('fii_net', 0):,.0f} Cr | DII: ₹{data.get('dii_net', 0):,.0f} Cr ({data.get('source', 'N/A')})")
        return data


# ═══════════════════════════════════════
# GAP 2: INDIA VIX LIVE
# ═══════════════════════════════════════

class VIXFetcher:
    """Fetch India VIX live value."""

    @staticmethod
    def fetch_from_yfinance() -> float:
        """Get India VIX via yfinance."""
        try:
            import yfinance as yf
            vix = yf.Ticker("^INDIAVIX")
            hist = vix.history(period="1d")
            if not hist.empty:
                val = hist["Close"].iloc[-1]
                logger.info(f"📊 India VIX: {val:.2f} (yfinance)")
                return float(val)
        except Exception as e:
            logger.warning(f"yfinance VIX failed: {e}")
        return 0

    @staticmethod
    def fetch_from_nse() -> float:
        """Fallback: NSE website."""
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            session.get("https://www.nseindia.com", timeout=10)
            resp = session.get("https://www.nseindia.com/api/allIndices", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for idx in data.get("data", []):
                    if "VIX" in idx.get("index", "").upper():
                        val = float(idx.get("last", 0))
                        logger.info(f"📊 India VIX: {val:.2f} (NSE)")
                        return val
        except Exception as e:
            logger.warning(f"NSE VIX failed: {e}")
        return 0

    @staticmethod
    def fetch() -> float:
        val = VIXFetcher.fetch_from_yfinance()
        if val == 0:
            val = VIXFetcher.fetch_from_nse()
        return val


# ═══════════════════════════════════════
# GAP 3: OPTION CHAIN OI DATA
# ═══════════════════════════════════════

class OptionChainFetcher:
    """Fetch live Nifty/BankNifty option chain from NSE."""

    @staticmethod
    def fetch(symbol: str = "NIFTY") -> Dict:
        """Fetch option chain data from NSE India website."""
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            session.headers["Referer"] = "https://www.nseindia.com/option-chain"

            # Get cookies first
            session.get("https://www.nseindia.com", timeout=10)

            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
            resp = session.get(url, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"Option chain fetch failed: HTTP {resp.status_code}")
                return OptionChainFetcher._empty_result()

            data = resp.json()
            records = data.get("records", {})
            chain_data = records.get("data", [])
            spot_price = records.get("underlyingValue", 0)

            if not chain_data:
                return OptionChainFetcher._empty_result()

            # Parse into structured format
            calls = []
            puts = []
            total_call_oi = 0
            total_put_oi = 0

            for record in chain_data:
                strike = record.get("strikePrice", 0)

                ce = record.get("CE", {})
                if ce:
                    ce_oi = ce.get("openInterest", 0)
                    total_call_oi += ce_oi
                    calls.append({
                        "strike": strike,
                        "oi": ce_oi,
                        "change_oi": ce.get("changeinOpenInterest", 0),
                        "ltp": ce.get("lastPrice", 0),
                        "volume": ce.get("totalTradedVolume", 0),
                        "iv": ce.get("impliedVolatility", 0),
                    })

                pe = record.get("PE", {})
                if pe:
                    pe_oi = pe.get("openInterest", 0)
                    total_put_oi += pe_oi
                    puts.append({
                        "strike": strike,
                        "oi": pe_oi,
                        "change_oi": pe.get("changeinOpenInterest", 0),
                        "ltp": pe.get("lastPrice", 0),
                        "volume": pe.get("totalTradedVolume", 0),
                        "iv": pe.get("impliedVolatility", 0),
                    })

            # Calculate key OI metrics
            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            # Max OI levels
            max_call_oi_strike = max(calls, key=lambda x: x["oi"])["strike"] if calls else 0
            max_put_oi_strike = max(puts, key=lambda x: x["oi"])["strike"] if puts else 0

            # Max Pain calculation
            max_pain = OptionChainFetcher._calculate_max_pain(calls, puts, spot_price)

            # Change in OI analysis
            max_call_oi_change = max(calls, key=lambda x: abs(x["change_oi"])) if calls else {}
            max_put_oi_change = max(puts, key=lambda x: abs(x["change_oi"])) if puts else {}

            result = {
                "symbol": symbol,
                "spot": spot_price,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "pcr": round(pcr, 2),
                "pcr_bias": "BULLISH" if pcr > 1.2 else "BEARISH" if pcr < 0.8 else "NEUTRAL",
                "resistance": max_call_oi_strike,
                "support": max_put_oi_strike,
                "max_pain": max_pain,
                "call_oi_buildup": max_call_oi_change.get("strike", 0) if max_call_oi_change else 0,
                "put_oi_buildup": max_put_oi_change.get("strike", 0) if max_put_oi_change else 0,
                "atm_iv": OptionChainFetcher._get_atm_iv(calls, puts, spot_price),
                "calls": calls,
                "puts": puts,
                "source": "NSE",
            }

            logger.info(
                f"📊 OI Chain ({symbol}): PCR={result['pcr']} ({result['pcr_bias']}) | "
                f"Support={result['support']} | Resistance={result['resistance']} | "
                f"Max Pain={result['max_pain']} | ATM IV={result['atm_iv']:.1f}%"
            )
            return result

        except Exception as e:
            logger.warning(f"Option chain fetch error: {e}")
            return OptionChainFetcher._empty_result()

    @staticmethod
    def _calculate_max_pain(calls, puts, spot):
        """Max Pain = strike where option buyers lose maximum money."""
        if not calls or not puts:
            return 0

        strikes = sorted(set(c["strike"] for c in calls))
        min_pain = float("inf")
        max_pain_strike = 0

        for test_strike in strikes:
            call_pain = sum(max(0, test_strike - c["strike"]) * c["oi"] for c in calls)
            put_pain = sum(max(0, p["strike"] - test_strike) * p["oi"] for p in puts)
            total_pain = call_pain + put_pain

            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_strike

        return max_pain_strike

    @staticmethod
    def _get_atm_iv(calls, puts, spot):
        """Get IV of ATM options."""
        if not calls:
            return 0
        atm_call = min(calls, key=lambda x: abs(x["strike"] - spot))
        return atm_call.get("iv", 0)

    @staticmethod
    def _empty_result():
        return {
            "symbol": "", "spot": 0, "pcr": 0, "pcr_bias": "UNKNOWN",
            "resistance": 0, "support": 0, "max_pain": 0,
            "total_call_oi": 0, "total_put_oi": 0,
            "atm_iv": 0, "calls": [], "puts": [], "source": "UNAVAILABLE",
        }


# ═══════════════════════════════════════
# GAP 6 (partial): CRUDE OIL PRICE
# ═══════════════════════════════════════

class CrudeFetcher:
    """Fetch Brent crude oil price."""

    @staticmethod
    def fetch() -> float:
        try:
            import yfinance as yf
            brent = yf.Ticker("BZ=F")
            hist = brent.history(period="1d")
            if not hist.empty:
                val = float(hist["Close"].iloc[-1])
                logger.info(f"🛢️ Brent Crude: ${val:.2f}")
                return val
        except Exception as e:
            logger.warning(f"Crude fetch failed: {e}")
        return 0


# ═══════════════════════════════════════
# MASTER FETCHER — One call gets everything
# ═══════════════════════════════════════

class LiveDataHub:
    """Single entry point for all live data feeds."""

    def __init__(self):
        self.fii_dii = {}
        self.vix = 0
        self.crude = 0
        self.option_chain = {}
        self.last_fetch = None

    def fetch_all(self, symbol="NIFTY") -> Dict:
        """Fetch all live data in one call."""
        logger.info("📡 Fetching all live data feeds...")

        self.fii_dii = FIIDIIFetcher.fetch()
        self.vix = VIXFetcher.fetch()
        self.crude = CrudeFetcher.fetch()
        self.option_chain = OptionChainFetcher.fetch(symbol)
        self.last_fetch = datetime.now()

        return {
            "fii_net": self.fii_dii.get("fii_net", 0),
            "dii_net": self.fii_dii.get("dii_net", 0),
            "vix": self.vix,
            "crude": self.crude,
            "pcr": self.option_chain.get("pcr", 0),
            "pcr_bias": self.option_chain.get("pcr_bias", "UNKNOWN"),
            "oi_support": self.option_chain.get("support", 0),
            "oi_resistance": self.option_chain.get("resistance", 0),
            "max_pain": self.option_chain.get("max_pain", 0),
            "atm_iv": self.option_chain.get("atm_iv", 0),
            "spot": self.option_chain.get("spot", 0),
        }

    def get_summary_text(self) -> str:
        """Human-readable summary for Telegram."""
        d = self.fii_dii
        oc = self.option_chain
        return (
            f"📊 <b>LIVE DATA FEEDS</b>\n\n"
            f"<b>FII:</b> ₹{d.get('fii_net', 0):,.0f} Cr | <b>DII:</b> ₹{d.get('dii_net', 0):,.0f} Cr\n"
            f"<b>India VIX:</b> {self.vix:.2f}\n"
            f"<b>Brent Crude:</b> ${self.crude:.2f}\n\n"
            f"<b>Option Chain ({oc.get('symbol', 'N/A')}):</b>\n"
            f"  PCR: {oc.get('pcr', 0):.2f} ({oc.get('pcr_bias', 'N/A')})\n"
            f"  OI Support: {oc.get('support', 0):,}\n"
            f"  OI Resistance: {oc.get('resistance', 0):,}\n"
            f"  Max Pain: {oc.get('max_pain', 0):,}\n"
            f"  ATM IV: {oc.get('atm_iv', 0):.1f}%\n"
        )
