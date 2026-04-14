# -*- coding: utf-8 -*-
"""
GX TradeIntel v5 — THE CONDUCTOR SYSTEM
==========================================
10 skills embedded. 3 strategy engines. 1 AI brain.
First-of-its-kind in Indian retail trading.

Skills: trading-intelligence, options-mastery-india, market-microstructure-india,
trade-psychology-capital, smartapi-integration, price-action-patterns,
backtesting-performance, market-regime-detection, mean-reversion-nifty, ai-conductor
"""
import os
from datetime import time

# ═══════════════════════════════════════
# [KEY] CREDENTIALS
# ═══════════════════════════════════════
# Credentials are loaded from .credentials.json (created by start.py --setup)
# You can also set environment variables to override

import json as _json
from pathlib import Path as _Path

def _load_creds():
    """Load credentials from .credentials.json file."""
    creds_file = _Path(__file__).parent / ".credentials.json"
    if creds_file.exists():
        with open(creds_file, encoding="utf-8") as f:
            return _json.load(f)
    return {}

_creds = _load_creds()

# BROKER SELECTION: "ANGEL" or "ZERODHA"
BROKER = "ANGEL"

# Angel One SmartAPI
ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY") or _creds.get("ANGEL_API_KEY", "")
ANGEL_CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID") or _creds.get("ANGEL_CLIENT_ID", "")
ANGEL_PASSWORD = os.environ.get("ANGEL_PASSWORD") or _creds.get("ANGEL_PASSWORD", "")
ANGEL_TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET") or _creds.get("ANGEL_TOTP_SECRET", "")

# Zerodha Kite Connect
ZERODHA_API_KEY = os.environ.get("ZERODHA_API_KEY") or _creds.get("ZERODHA_API_KEY", "")
ZERODHA_API_SECRET = os.environ.get("ZERODHA_API_SECRET") or _creds.get("ZERODHA_API_SECRET", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or _creds.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _creds.get("TELEGRAM_CHAT_ID", "")

# Claude AI
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or _creds.get("ANTHROPIC_API_KEY", "")

# ═══════════════════════════════════════
# [CAPITAL] CAPITAL & RISK — DYNAMIC SCALING
# Works for ANY capital: ₹10K, ₹1L, ₹10L, ₹1Cr
# ALL limits are PERCENTAGE-BASED, not fixed amounts
# Just change TOTAL_CAPITAL — everything else auto-scales
# ═══════════════════════════════════════
TOTAL_CAPITAL = 10000              # ← CHANGE THIS TO YOUR CAPITAL. That's it.

# Risk percentages (auto-scale with capital)
MAX_RISK_PER_TRADE_PCT = 2.5      # 2.5% of capital per trade
MAX_CAPITAL_PER_TRADE_PCT = 30    # Max 30% of capital on one position (buffer for fees/slippage)
MAX_DAILY_LOSS_PCT = 7.5          # Stop trading if down 7.5% in a day
MAX_WEEKLY_LOSS_PCT = 15          # Stop trading if down 15% in a week

# Computed values (auto-calculated — DON'T hardcode these)
MAX_RISK_PER_TRADE = TOTAL_CAPITAL * (MAX_RISK_PER_TRADE_PCT / 100)
MAX_DAILY_LOSS = TOTAL_CAPITAL * (MAX_DAILY_LOSS_PCT / 100)
MAX_WEEKLY_LOSS = TOTAL_CAPITAL * (MAX_WEEKLY_LOSS_PCT / 100)
MAX_CAPITAL_PER_TRADE = TOTAL_CAPITAL * (MAX_CAPITAL_PER_TRADE_PCT / 100)

# Trades per day scales with capital
# ₹10K = 1-2 trades | ₹50K = 2-3 trades | ₹1L+ = 3-4 trades
if TOTAL_CAPITAL < 25000:
    MAX_TRADES_PER_DAY = 2
elif TOTAL_CAPITAL < 100000:
    MAX_TRADES_PER_DAY = 3
elif TOTAL_CAPITAL < 500000:
    MAX_TRADES_PER_DAY = 4
else:
    MAX_TRADES_PER_DAY = 5

# Lot scaling: how many lots can you afford?
# ₹10K = 1 lot Nifty | ₹50K = 2-3 lots | ₹1L = 4-5 lots | ₹5L+ = 10+ lots
def max_lots(capital, premium, lot_size):
    """Calculate max lots affordable within risk limits."""
    max_spend = capital * (MAX_CAPITAL_PER_TRADE_PCT / 100)
    affordable = int(max_spend / (premium * lot_size)) if premium > 0 else 0
    return max(1, affordable)

# Instrument scaling: what can you trade at your capital level?
# ₹10K-25K:   Nifty options only (cheapest)
# ₹25K-1L:    Nifty + BankNifty options
# ₹1L-5L:     Above + equity delivery + swing trades
# ₹5L+:       Above + futures + multi-leg option strategies
if TOTAL_CAPITAL < 25000:
    TRADEABLE_INSTRUMENTS = ["NIFTY"]
elif TOTAL_CAPITAL < 100000:
    TRADEABLE_INSTRUMENTS = ["NIFTY", "BANKNIFTY"]
elif TOTAL_CAPITAL < 500000:
    TRADEABLE_INSTRUMENTS = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
else:
    TRADEABLE_INSTRUMENTS = ["NIFTY", "BANKNIFTY", "FINNIFTY"]

# Exit rule scaling
# Smaller capital = tighter targets (preserve capital)
# Larger capital = wider targets (ride bigger moves)
if TOTAL_CAPITAL < 25000:
    PROFIT_TARGET_1_PCT = 15       # Quick 15% for small capital
    PROFIT_TARGET_2_PCT = 30
    STOP_LOSS_PCT = 20             # Tight SL for small capital
    TRAILING_ACTIVATION_PCT = 10
    TIME_STOP_MINUTES = 60
elif TOTAL_CAPITAL < 100000:
    PROFIT_TARGET_1_PCT = 20       # Slightly wider for ₹25K-1L
    PROFIT_TARGET_2_PCT = 40
    STOP_LOSS_PCT = 25
    TRAILING_ACTIVATION_PCT = 12
    TIME_STOP_MINUTES = 75
else:
    PROFIT_TARGET_1_PCT = 25       # Ride trends for ₹1L+
    PROFIT_TARGET_2_PCT = 50
    STOP_LOSS_PCT = 25
    TRAILING_ACTIVATION_PCT = 15
    TIME_STOP_MINUTES = 90

TRAILING_DROP_FROM_PEAK = 10

# Strategy time controls
STRATEGY = {
    "no_new_entry_after": time(14, 45),   # No new trades after 2:45 PM
    "square_off_time": time(15, 15),      # Close all at 3:15 PM
    "scan_start": time(9, 30),            # Start scanning at 9:30 AM
}

# ═══════════════════════════════════════
# [AI] AI CONDUCTOR [ai-conductor]
# ═══════════════════════════════════════
CONDUCTOR = {
    "use_ai": True,                 # Use Claude API for decisions
    "model": "claude-sonnet-4-20250514",
    "fallback_to_rules": True,      # Use algorithmic fallback if API fails
    "recheck_at": [time(11, 30), time(13, 30)],
    "news_override_enabled": True,
    "min_conductor_confidence": 60, # Below this → NO_TRADE
}

# ═══════════════════════════════════════
# [DATA] REGIME DETECTION [market-regime-detection]
# ═══════════════════════════════════════
REGIME = {
    "adx_trending": 25,
    "adx_ranging": 20,
    "bb_expansion_threshold": 1.2,
    "atr_volatile_ratio": 1.5,
    "structure_lookback": 10,
    "min_regime_confidence": 50,
}

# ═══════════════════════════════════════
# [ENGINE1] ENGINE 1: MOMENTUM [trading-intelligence]
# For TRENDING markets. Target: 60-65% WR, high profit.
# ═══════════════════════════════════════
MOMENTUM = {
    "supertrend_period": 10, "supertrend_mult": 3,
    "ema_trend": 50, "ema_fast": 9, "ema_slow": 21,
    "adx_min": 25,
    "rsi_period": 14, "rsi_oversold": 28, "rsi_overbought": 72,
    "bb_period": 20, "bb_std": 2.0,
    "min_volume_ratio": 2.0,
    "min_confidence": 80,
    "require_15m_align": True,
    # Exits: Larger targets (ride the trend)
    "profit_target_1_pct": 25,
    "profit_target_2_pct": 45,
    "stop_loss_pct": 25,
    "trailing_activation_pct": 15,
    "time_stop_minutes": 90,
}

# ═══════════════════════════════════════
# [ENGINE2] ENGINE 2: MEAN REVERSION [mean-reversion-nifty]
# For RANGING markets. Target: 70-75% WR, consistent.
# ═══════════════════════════════════════
MEAN_REVERSION = {
    "rsi2_oversold": 10,             # Ultra-short RSI(2) < 10
    "rsi2_overbought": 90,
    "vwap_deviation_pct": 0.3,       # Min 0.3% from VWAP
    "vwap_strong_deviation": 0.5,
    "bb_period": 20, "bb_std": 2.0,
    "min_volume_ratio": 1.5,         # Lower vol needed (ranging = less vol)
    "require_volume_exhaustion": True,
    "require_candle_pattern": True,
    "require_near_sr": True,
    "min_confidence": 70,
    # Exits: Smaller targets (quick capture)
    "profit_target_pct": 15,         # Quick 15% premium gain
    "stop_loss_pct": 20,             # Tight 20% stop
    "trailing_activation_pct": 8,
    "time_stop_minutes": 45,         # Fast — if no reversion in 45m, exit
    "target_vwap": True,             # Target = VWAP price (natural reversion level)
}

# ═══════════════════════════════════════
# [ENGINE3] ENGINE 3: SCALPER [price-action-patterns]
# For VOLATILE markets. Target: 60% WR, quick profits.
# ═══════════════════════════════════════
SCALPER = {
    "orb_minutes": 15,
    "orb_max_range": 100,            # Skip if ORB range > 100 pts
    "orb_target_mult": 1.5,
    "vwap_bounce_pct": 0.15,
    "min_volume_ratio": 2.0,
    "min_confidence": 70,
    # Exits: Quickest targets
    "profit_target_pct": 10,         # Quick 10% capture
    "stop_loss_pct": 15,             # Very tight
    "trailing_activation_pct": 5,
    "time_stop_minutes": 30,         # 30 min max hold
}

# ═══════════════════════════════════════
# [OPTIONS] OPTIONS [options-mastery-india]
# ═══════════════════════════════════════
OPTIONS = {
    "prefer_atm": True, "max_otm_strikes": 1,
    "min_oi": 50000, "max_bid_ask_spread": 2.0,
    "min_premium": 40, "max_premium": 200,
    "avoid_expiry_day": True,
    "best_days": ["Monday", "Tuesday", "Wednesday", "Friday"],
    "pcr_bullish": 1.2, "pcr_bearish": 0.8,
}

# ═══════════════════════════════════════
# [MACRO] MACRO [market-microstructure-india]
# ═══════════════════════════════════════
MACRO = {
    # FII thresholds
    "fii_negligible": 500, "fii_negligible_cr": 500,
    "fii_moderate_cr": 1500,
    "fii_significant": 3000, "fii_significant_cr": 3000,
    # VIX thresholds
    "vix_low": 12, "vix_normal_low": 12,
    "vix_high": 20, "vix_normal_high": 20,
    "vix_panic": 25, "vix_elevated": 25,
    "vix_reduce_size_above": 25,
    # Crude thresholds
    "crude_positive_below": 75,
    "crude_neutral_below": 85,
    "crude_cautionary_below": 100,
    "crude_caution_above": 100,
    # Gap thresholds
    "gap_small_pct": 0.3,
    "gap_full_pct": 0.8,
    "gap_large_pct": 1.5,
    "gap_fill_prob_full": 30,
    "gap_fill_prob_partial": 55,
    "gap_fill_prob_small": 75,
}

# ═══════════════════════════════════════
# [BACKTEST] BACKTEST COSTS [backtesting-performance]
# ═══════════════════════════════════════
BACKTEST = {
    "brokerage_per_order": 20, "stt_sell_pct": 0.0625,
    "gst_pct": 18, "slippage_per_unit": 1.5,
    "min_trades_for_live": 15, "min_win_rate": 55,
    "min_profit_factor": 1.3, "max_drawdown_pct": 15,
}

# ═══════════════════════════════════════
# [AI] PSYCHOLOGY [trade-psychology-capital]
# ═══════════════════════════════════════
PSYCHOLOGY = {
    "red_flag_checks": True,
    "max_consecutive_losses": 3,
    "cooldown_after_loss_streak": 30,
    "revenge_trade_block": True,
}

# ═══════════════════════════════════════
# [OPTIONS] INSTRUMENTS [smartapi-integration]
# ═══════════════════════════════════════
# All tradeable instruments — bot scans ALL active ones and picks the best setup
INSTRUMENTS = {
    # ── INDICES (Options) ──
    "NIFTY": {"token": "99926000", "exchange": "NSE", "lot_size": 25, "strike_gap": 50, "type": "INDEX"},
    "BANKNIFTY": {"token": "99926009", "exchange": "NSE", "lot_size": 15, "strike_gap": 100, "type": "INDEX"},
    "FINNIFTY": {"token": "99926037", "exchange": "NSE", "lot_size": 25, "strike_gap": 50, "type": "INDEX"},
    "MIDCPNIFTY": {"token": "99926074", "exchange": "NSE", "lot_size": 50, "strike_gap": 25, "type": "INDEX"},
    "SENSEX": {"token": "99919000", "exchange": "BSE", "lot_size": 10, "strike_gap": 100, "type": "INDEX"},

    # ── TOP STOCKS (F&O — high liquidity options) ──
    "RELIANCE": {"token": "2885", "exchange": "NSE", "lot_size": 250, "strike_gap": 20, "type": "STOCK"},
    "TCS": {"token": "11536", "exchange": "NSE", "lot_size": 175, "strike_gap": 50, "type": "STOCK"},
    "HDFCBANK": {"token": "1333", "exchange": "NSE", "lot_size": 550, "strike_gap": 20, "type": "STOCK"},
    "INFY": {"token": "1594", "exchange": "NSE", "lot_size": 300, "strike_gap": 25, "type": "STOCK"},
    "ICICIBANK": {"token": "4963", "exchange": "NSE", "lot_size": 700, "strike_gap": 10, "type": "STOCK"},
    "SBIN": {"token": "3045", "exchange": "NSE", "lot_size": 750, "strike_gap": 10, "type": "STOCK"},
    "BAJFINANCE": {"token": "317", "exchange": "NSE", "lot_size": 125, "strike_gap": 50, "type": "STOCK"},
    "ITC": {"token": "1660", "exchange": "NSE", "lot_size": 1600, "strike_gap": 5, "type": "STOCK"},
    "TATAMOTORS": {"token": "3456", "exchange": "NSE", "lot_size": 575, "strike_gap": 10, "type": "STOCK"},
    "AXISBANK": {"token": "5900", "exchange": "NSE", "lot_size": 625, "strike_gap": 10, "type": "STOCK"},
    "KOTAKBANK": {"token": "1922", "exchange": "NSE", "lot_size": 400, "strike_gap": 20, "type": "STOCK"},
    "LT": {"token": "11483", "exchange": "NSE", "lot_size": 150, "strike_gap": 25, "type": "STOCK"},
    "TATASTEEL": {"token": "3499", "exchange": "NSE", "lot_size": 1500, "strike_gap": 5, "type": "STOCK"},
    "MARUTI": {"token": "10999", "exchange": "NSE", "lot_size": 100, "strike_gap": 100, "type": "STOCK"},
    "ADANIENT": {"token": "25", "exchange": "NSE", "lot_size": 250, "strike_gap": 25, "type": "STOCK"},
}

# Which instruments to actively scan (picks from TRADEABLE_INSTRUMENTS)
# Bot scans ALL of these, runs regime + strategy on each, and picks the BEST setup
ACTIVE_INSTRUMENTS = TRADEABLE_INSTRUMENTS  # Controlled by capital tier above

# Primary instrument for regime detection (index gives cleanest market read)
PRIMARY_INSTRUMENT = "NIFTY"

# Multi-instrument settings
MULTI_INSTRUMENT = {
    "enabled": True,                    # Scan multiple instruments
    "max_simultaneous_positions": 2,    # Max open positions at once
    "prefer_index": True,               # Prefer index options over stock options
    "min_option_oi": 50000,             # Min OI for stock options (liquidity filter)
    "capital_per_position_pct": 40,     # Max 40% capital per position
}

# ═══════════════════════════════════════
# [TIME] TIMING
# ═══════════════════════════════════════
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
SCAN_START = time(9, 20)
SQUARE_OFF = time(15, 20)
GOLDEN_START = time(9, 25)
GOLDEN_END = time(11, 15)
DEAD_START = time(11, 30)
DEAD_END = time(13, 30)
SCAN_INTERVAL_GOLDEN = 45
SCAN_INTERVAL_NORMAL = 90
SCAN_INTERVAL_DEAD = 300
NEWS_REFRESH = 600
SESSION_REFRESH = 7200

# ═══════════════════════════════════════
# [SYSTEM] SYSTEM
# ═══════════════════════════════════════
PAPER_TRADE = True
LOG_DIR = "logs"
LOG_LEVEL = "INFO"

# ═══════════════════════════════════════
# [MODE] EXECUTION MODE [ChatGPT: "add manual mode"]
# ═══════════════════════════════════════
# "AUTO"    = Bot executes trades automatically (full auto)
# "SUGGEST" = Bot generates signals + sends Telegram but YOU place the trade
# Start with SUGGEST to build trust, switch to AUTO when confident
EXECUTION_MODE = "AUTO"

# ═══════════════════════════════════════
# [RESERVE] CAPITAL RESERVE [ChatGPT: "70% active, 30% reserve"]
# ═══════════════════════════════════════
ACTIVE_CAPITAL_PCT = 70            # Only use 70% for trading
RESERVE_PCT = 30                   # 30% always untouched as safety buffer
ACTIVE_CAPITAL = TOTAL_CAPITAL * (ACTIVE_CAPITAL_PCT / 100)
# When drawdown hits 10%, reduce active to 50%
DRAWDOWN_REDUCE_THRESHOLD = 10     # % drawdown to trigger reduction
DRAWDOWN_REDUCED_ACTIVE_PCT = 50   # Reduce to 50% active when in drawdown

# ═══════════════════════════════════════
# [SAFETY] KILL SWITCH [ChatGPT: "what if API fails?"]
# ═══════════════════════════════════════
KILL_SWITCH = {
    "max_api_errors": 5,           # Consecutive API failures → kill
    "max_slippage_violations": 3,  # Bad fills → kill
    "max_slippage_pct": 2.0,       # Max acceptable slippage per fill
    "stale_data_minutes": 5,       # No data for 5 min → kill
    "market_crash_pct": 5.0,       # 5% move from prev close → kill
    "vix_panic_level": 35,         # VIX > 35 → kill
}

# ═══════════════════════════════════════
# [DATA] VALIDATION [ChatGPT: "2 weeks is not enough"]
# ═══════════════════════════════════════
VALIDATION = {
    "min_trades_for_live": 30,     # Was 15. ChatGPT said 30-50. Using 30.
    "min_paper_days": 20,          # ~4 weeks paper trading
    "min_win_rate": 50,
    "min_profit_factor": 1.3,
    "max_drawdown_pct": 15,
    "min_expectancy_positive": True,
    "min_regime_accuracy": 60,     # ChatGPT: "accuracy ≥ 60% or engine is useless"
    "min_sharpe": 0.5,
}

