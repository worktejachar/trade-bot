# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — Zerodha Free Login (Selenium)
===================================================
Feature 2: Login to Zerodha WITHOUT paying ₹2,000/month for Kite Connect API.
Uses Selenium to automate browser login and extract session token.
Based on open-source approach from srikar-kodakandla & iRavinderBrar repos.

SAVES: ₹2,000/month (₹24,000/year)

Prerequisites:
  pip install selenium webdriver-manager requests
  Chrome browser installed

Usage:
  from zerodha_free import ZerodhaFreeLogin
  token = ZerodhaFreeLogin.login("user_id", "password", "totp_secret")
"""
import os
import json
import logging
import time as t_
from datetime import datetime
from typing import Optional

import requests
import pyotp

logger = logging.getLogger("GXTradeIntel.ZerodhaFree")


class ZerodhaFreeLogin:
    """Login to Zerodha Kite using Selenium — no paid API needed."""

    BASE_URL = "https://kite.zerodha.com"

    @staticmethod
    def login(user_id: str, password: str, totp_secret: str) -> Optional[str]:
        """
        Login and return enctoken for session.

        Method 1: Try requests-based login (no browser needed)
        Method 2: Fall back to Selenium if Method 1 fails
        """
        # Try Method 1 first (faster, no browser)
        token = ZerodhaFreeLogin._login_requests(user_id, password, totp_secret)
        if token:
            return token

        # Method 2: Selenium
        token = ZerodhaFreeLogin._login_selenium(user_id, password, totp_secret)
        return token

    @staticmethod
    def _login_requests(user_id: str, password: str, totp_secret: str) -> Optional[str]:
        """Login using pure requests (no browser)."""
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Kite-Version": "3.0.0",
            })

            # Step 1: Get login page (for cookies)
            session.get(f"{ZerodhaFreeLogin.BASE_URL}/connect/login")

            # Step 2: Submit credentials
            totp = pyotp.TOTP(totp_secret).now()
            login_resp = session.post(
                "https://kite.zerodha.com/api/login",
                data={"user_id": user_id, "password": password},
            )

            if login_resp.status_code != 200:
                logger.warning(f"Login step 1 failed: {login_resp.status_code}")
                return None

            login_data = login_resp.json()
            request_id = login_data.get("data", {}).get("request_id", "")

            if not request_id:
                logger.warning("No request_id in login response")
                return None

            # Step 3: Submit TOTP
            twofa_resp = session.post(
                "https://kite.zerodha.com/api/twofa",
                data={
                    "user_id": user_id,
                    "request_id": request_id,
                    "twofa_value": totp,
                    "twofa_type": "totp",
                },
            )

            if twofa_resp.status_code != 200:
                logger.warning(f"TOTP step failed: {twofa_resp.status_code}")
                return None

            # Extract enctoken from cookies
            enctoken = session.cookies.get("enctoken", "")
            if enctoken:
                logger.info(f"✅ Zerodha FREE login successful for {user_id}")
                ZerodhaFreeLogin._save_token(enctoken)
                return enctoken

            logger.warning("No enctoken in cookies")
            return None

        except Exception as e:
            logger.warning(f"Requests login failed: {e}")
            return None

    @staticmethod
    def _login_selenium(user_id: str, password: str, totp_secret: str) -> Optional[str]:
        """Fallback: Login using Selenium browser automation."""
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
            except Exception:
                service = Service()

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")

            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 15)

            try:
                # Open login page
                driver.get("https://kite.zerodha.com/connect/login?v=3&api_key=kitefront")
                t_.sleep(2)

                # Enter user ID
                uid_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
                uid_field.send_keys(user_id)

                # Enter password
                pwd_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                pwd_field.send_keys(password)

                # Click login
                login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                login_btn.click()
                t_.sleep(3)

                # Enter TOTP
                totp = pyotp.TOTP(totp_secret).now()
                totp_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
                totp_field.send_keys(totp)
                t_.sleep(1)

                # Click verify (or auto-submit)
                try:
                    verify_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    verify_btn.click()
                except Exception:
                    pass

                t_.sleep(3)

                # Extract enctoken from cookies
                cookies = driver.get_cookies()
                for cookie in cookies:
                    if cookie["name"] == "enctoken":
                        enctoken = cookie["value"]
                        logger.info(f"✅ Zerodha FREE login (Selenium) successful")
                        ZerodhaFreeLogin._save_token(enctoken)
                        return enctoken

                logger.warning("No enctoken found in Selenium cookies")
                return None

            finally:
                driver.quit()

        except ImportError:
            logger.error("Selenium not installed. Run: pip install selenium webdriver-manager")
            return None
        except Exception as e:
            logger.error(f"Selenium login failed: {e}")
            return None

    @staticmethod
    def _save_token(enctoken: str):
        """Save token for same-day reuse."""
        token_file = os.path.join("logs", "zerodha_enctoken.json")
        os.makedirs("logs", exist_ok=True)
        with open(token_file, "w") as f:
            json.dump({
                "enctoken": enctoken,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
            }, f)

    @staticmethod
    def load_saved_token() -> Optional[str]:
        """Load today's saved token if exists."""
        token_file = os.path.join("logs", "zerodha_enctoken.json")
        if not os.path.exists(token_file):
            return None
        try:
            with open(token_file) as f:
                data = json.load(f)
            if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                logger.info("✅ Using saved Zerodha enctoken from today")
                return data["enctoken"]
        except Exception:
            pass
        return None


class KiteApp:
    """Zerodha Kite API using enctoken (FREE, no paid API subscription).
    Based on iRavinderBrar's approach."""

    def __init__(self, enctoken: str):
        self.enctoken = enctoken
        self.base = "https://kite.zerodha.com/oms"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"enctoken {enctoken}",
            "User-Agent": "Mozilla/5.0",
        })

    def profile(self):
        return self._get("/user/profile")

    def margins(self):
        return self._get("/user/margins")

    def orders(self):
        return self._get("/orders")

    def positions(self):
        return self._get("/portfolio/positions")

    def holdings(self):
        return self._get("/portfolio/holdings")

    def quote(self, instruments):
        """Get quote. instruments = 'NSE:NIFTY 50' or 'NFO:NIFTY...'"""
        if isinstance(instruments, str):
            instruments = [instruments]
        data = self._get("/quote", params={"i": instruments})
        return data

    def ltp(self, instruments):
        if isinstance(instruments, str):
            instruments = [instruments]
        return self._get("/quote/ltp", params={"i": instruments})

    def historical_data(self, instrument_token, from_date, to_date, interval, continuous=False, oi=False):
        params = {"from": from_date, "to": to_date, "continuous": int(continuous), "oi": int(oi)}
        data = self._get(f"/instruments/historical/{instrument_token}/{interval}", params=params)
        return data.get("candles", []) if data else []

    def instruments(self, exchange=None):
        url = f"https://api.kite.trade/instruments"
        if exchange:
            url += f"/{exchange}"
        resp = self.session.get(url)
        if resp.status_code == 200:
            import csv, io
            reader = csv.DictReader(io.StringIO(resp.text))
            return list(reader)
        return []

    def place_order(self, **params):
        return self._post("/orders/regular", data=params)

    def modify_order(self, order_id, **params):
        return self._put(f"/orders/regular/{order_id}", data=params)

    def cancel_order(self, order_id):
        return self._delete(f"/orders/regular/{order_id}")

    def _get(self, endpoint, params=None):
        try:
            resp = self.session.get(f"{self.base}{endpoint}", params=params)
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception as e:
            logger.error(f"KiteApp GET error: {e}")
        return {}

    def _post(self, endpoint, data=None):
        try:
            resp = self.session.post(f"{self.base}{endpoint}", data=data)
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("order_id", "")
        except Exception as e:
            logger.error(f"KiteApp POST error: {e}")
        return ""

    def _put(self, endpoint, data=None):
        try:
            resp = self.session.put(f"{self.base}{endpoint}", data=data)
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception as e:
            logger.error(f"KiteApp PUT error: {e}")
        return {}

    def _delete(self, endpoint):
        try:
            resp = self.session.delete(f"{self.base}{endpoint}")
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception as e:
            logger.error(f"KiteApp DELETE error: {e}")
        return {}
