# GX TradeIntel v6 — AI-Powered Trading Bot for Indian Markets

> **Crafted by [GarudawnX](https://garudawnx.com)** | Built with Claude AI

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**GX TradeIntel** is a fully automated, multi-instrument options trading bot for Indian stock markets (NSE/BSE). It uses AI-powered regime detection, multi-strategy selection, and adaptive risk management to trade options on **5 indices + 15 top F&O stocks** via Angel One SmartAPI and Zerodha.

---

## Performance Status

### v6 Final Backtest (Daily Candles, 3 Engines, 2 Years)

```
═══════════════════════════════════════
  Win Rate:      66.1%
  Profit Factor: 3.16
  Net Profit:    Rs +12,764 on Rs 10,000 (+127.6%)
  Avg Winner:    Rs 456 per trade
  Avg Loser:     Rs 282 per trade
  Risk/Reward:   1:1.62
  Max Drawdown:  9.5%
  Expectancy:    Rs 206 per trade
  Trades:        62 (W:41, L:21)
  Final Equity:  Rs 22,764
═══════════════════════════════════════
  Walk-Forward:  WFE 0.49 (borderline)
  Monte Carlo:   100% profitable, 0% ruin
═══════════════════════════════════════
```

### Engine Breakdown

| Engine | Trades | Win Rate | Net P&L | What It Does |
|---|---|---|---|---|
| **Momentum** | 37 | 67.6% | +Rs 9,225 | Pullback entries in ADX>25 trends |
| **Mean Reversion** | 25 | 64.0% | +Rs 3,539 | RSI/BB/VWAP snap-back in ranging |
| **Scalper** | 0 | — | — | Range breakout + VWAP bounce (needs 5-min data) |

> Both active engines profitable individually. Scalper generates 0 trades on daily data — it needs 5-minute candles to detect ORB and VWAP bounces. This is expected and will only work in the live system.

### Monthly Consistency: 12 profitable / 4 losing months

### What the backtest CAN'T simulate (live advantages)
- 5-minute candles (daily is too coarse for scalper/MR entries)
- Real option chain data (IV, OI, Greeks, PCR)
- VIX-based regime adjustment
- AI conductor with news/sentiment context
- VWAP from actual tick data

**The live system may perform differently.** Paper trading is the only way to find out.

### Evolution (7 Iterations — Lessons in Honesty)

| Version | Win Rate | PF | Trades | Net Profit | Data | Key Change |
|---|---|---|---|---|---|---|
| v1 Basic | 44.4% | 1.43 | 187 | +Rs 6,447 | Daily | First working version |
| v2 Accuracy | 46.8% | 2.04 | 124 | +Rs 12,558 | Daily | Options P&L fix |
| v3 High WR | 57.1% | 2.82 | 35 | +Rs 4,393 | Daily | Confirmation filters |
| v4 Balanced | 52.7% | 1.78 | 91 | +Rs 6,874 | Daily | 6 setups added |
| v5 Aggressive | 52.7% | 1.78 | 91 | +Rs 13,452 | Daily | Compound + 3% risk (inflated) |
| v6 Conservative | 52.7% | 1.78 | 91 | +Rs 8,358 | Daily | 2% risk, theta-aware |
| **v6 Final** | **66.1%** | **3.16** | **62** | **+Rs 12,764** | **Daily** | **3 engines, conductor, lowered thresholds** |

> **Lesson:** v1-v5 had inflated returns due to mismatched setups and aggressive sizing. v6 Final keeps the 3-engine conductor architecture with honest risk (2%, theta-aware, slippage) and achieves the best results through higher-quality trade selection. The live system with real 5-min data, option chain, VIX, and AI sentiment will be the true test.

---

## What Makes This Different

| Feature | GX TradeIntel | Most Open-Source Bots |
|---|---|---|
| Return | +127.6% (daily backtest, 2% risk, all costs modeled) | Unknown |
| Instruments | 20 (5 indices + 15 stocks) | 1 (Nifty only) |
| AI Brain | Claude AI regime validation | None |
| Strategies | 3 engines + conductor selection | 1 fixed strategy |
| Risk Engine | Compound adaptive (4 factors) | Fixed % risk |
| Accuracy Filters | Confirmation + CPR + trend alignment | None |
| Robustness | Monte Carlo + walk-forward | Basic backtest |
| Indicators | 25+ (CPR, Z-score, VWAP bands, StochRSI) | 3-5 standard |
| Kill Switch | API failure + crash + VIX panic + DD | None |

---

## Tradeable Instruments (20)

### Indices
NIFTY 50 | BANK NIFTY | FIN NIFTY | MIDCAP NIFTY | SENSEX

### Top F&O Stocks
RELIANCE | TCS | HDFC BANK | INFOSYS | ICICI BANK | SBI | BAJAJ FINANCE | ITC | TATA MOTORS | AXIS BANK | KOTAK BANK | L&T | TATA STEEL | MARUTI | ADANI ENT

> Bot scans ALL active instruments and picks the **strongest signal** automatically.

---

## Architecture

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  MULTI-SCAN  │────>│  AI CONDUCTOR │────>│  3 STRATEGY  │
│  5 Indices   │     │  Regime Det.  │     │   ENGINES    │
│  15 Stocks   │     │  Claude API   │     │  Best Signal │
│  Live Data   │     │  Rule Fallback│     │  Across All  │
└──────────────┘     └───────────────┘     └──────┬───────┘
       │                                           │
       ▼                                           ▼
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  25+ INDIC.  │     │  COMPOUND     │     │  SAFETY      │
│  Z-Score,CPR │     │  RISK ENGINE  │     │  Kill Switch │
│  VWAP Bands  │     │  2% Equity    │     │  Event Cal.  │
│  StochRSI    │     │  Up to 5 lots │     │  DD Guard    │
└──────────────┘     └───────────────┘     └──────────────┘
       │                                           │
       ▼                                           ▼
┌──────────────┐     ┌───────────────┐
│  BROKER API  │────>│  TELEGRAM     │
│  Angel One   │     │  9 Commands   │
│  Zerodha     │     │  Daily Report │
└──────────────┘     └───────────────┘
```

---

## Quick Start

```bash
git clone https://github.com/worktejachar/trade-bot.git
cd trade-bot
pip install -r requirements.txt
python3 start.py --setup
python3 start.py --test
python3 backtest.py          # See proof
python3 start.py             # Start paper trading
```

---

## Accuracy Filters

| Filter | Impact |
|---|---|
| **Confirmation Candle** | MANDATORY — no entry without green/red candle proof |
| **CPR Confluence** | Entry near Pivot/S1/R1 = +15 score |
| **RSI Agreement** | RSI must confirm direction |
| **Volume Confirmation** | Min 1.5-2.0x average volume |

## 3 Strategy Engines (Matching Live System)

| Engine | Target Market | Min Confidence | Entry Logic |
|---|---|---|---|
| **Momentum** | ADX > 25 (trending) | 50 | SuperTrend + EMA50 + RSI pullback + volume |
| **Mean Reversion** | ADX < 30 (ranging) | 50 | RSI(2) extreme + BB touch + VWAP deviation |
| **Scalper** | High ATR (volatile) | 50 | Range breakout + VWAP bounce + volume spike |

> Conductor picks ONE engine per bar based on ADX — same logic as live `conductor.py`.

## Risk Management

| Feature | Setting |
|---|---|
| **Risk Per Trade** | 2% of current equity (compounds) |
| **High Confidence (70+)** | 1.2x size multiplier |
| **Max Lots** | 5 per trade |
| **Stop Loss** | 20% of premium (theta-adjusted) |
| **Target** | 30% max (trail winners) |
| **Drawdown Guard** | 5%→normal, 10%→half, 15%→quarter, 20%→STOP |
| **Kill Switch** | API failure, VIX panic, 15min no heartbeat |
| **Event Calendar** | RBI, Budget, FOMC, Election → auto skip |
| **Consec Loss Pause** | 3 losses → pause, 4 → stop day |

## Telegram Commands

```
/status /pnl /feeds /regime /signal /stop /resume /health /help
```

## Capital Scaling

| Capital | Risk/Trade | Instruments | Trades/Day |
|---|---|---|---|
| 10K | 300 | Nifty | 2 |
| 25K-1L | 750-3,000 | Nifty + BankNifty | 3 |
| 1L-5L | 3,000-15,000 | 3 Indices | 4 |
| 5L+ | 15,000-50,000 | All 20 | 5 |

---

## File Structure (34 files, 7,700+ lines)

```
trade-bot/
├── main.py              # Multi-instrument orchestrator
├── backtest.py          # Daily backtest (3 engines, conductor, walk-forward)
├── config.py            # 20 instruments, compound scaling
├── indicators.py        # 25+ indicators (CPR, Z-Score, VWAP, StochRSI)
├── adaptive_risk.py     # 4-factor compound risk engine
├── robustness.py        # Noise injection, sensitivity, WFE
├── engines/             # MR Z-Score, Momentum, Scalper
├── broker.py            # Angel One SmartAPI
├── broker_multi.py      # Multi-broker + crash recovery
├── zerodha_free.py      # Free Zerodha login
├── risk_manager.py      # MTM exits, trailing, psychology
├── kill_switch.py       # Emergency stop
├── safety.py            # Event calendar, safe hours, watchdog
├── live_feeds.py        # FII/DII, VIX, OI, Crude
├── sentiment.py         # News + AI sentiment
├── alerts.py            # Telegram alerts
├── telegram_cmd.py      # 9 commands
├── post_market.py       # Daily report card
└── ... (34 files total)
```

---

## Robustness Testing

Noise Injection | Parameter Sensitivity | Entry Delay | Walk-Forward (WFE 0.49, borderline) | Monte Carlo (100% profitable, 0% ruin)

> **Note:** Backtest uses daily candles with the same conductor + 3-engine logic as the live system. Paper trade 200+ trades before going live.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Help needed: Web dashboard, Greeks tracking, Options spreads, Docker, More instruments.

## Acknowledgments

[openalgo](https://github.com/marketcalls/openalgo) | [vectorbt-backtesting-skills](https://github.com/marketcalls/vectorbt-backtesting-skills) | [srikar-kodakandla](https://github.com/srikar-kodakandla/fully-automated-nifty-options-trading) | [zerobha](https://github.com/althk/zerobha) | [buzzsubash](https://github.com/buzzsubash/algo_trading_strategies_india)

## Disclaimer

**Educational purposes only.** Trading involves significant risk. Past performance ≠ future results. **Trade at your own risk.**

## License

MIT — See [LICENSE](LICENSE)

---

**Built by [GarudawnX](https://garudawnx.com)❤️| Powered by [Claude AI](https://anthropic.com)**

⭐️ Star this repo if you find it useful!
