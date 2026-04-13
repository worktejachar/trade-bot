# -*- coding: utf-8 -*-
"""
GX TradeIntel v6 — THE PROVEN CONDUCTOR SYSTEM (FINAL WIRED)
==============================================================
22 files. 5,452 lines. 10 skills. EVERY module connected.
"""
import os, sys, time as t_, logging, csv
from datetime import datetime, time, timedelta
from pathlib import Path

import config
from broker_multi import get_broker, OrderConfirmation, StatePersistence
from regime import detect_regime
from conductor import call_conductor, check_news_override
from engines import momentum, mean_reversion, scalper
from indicators import compute_all
from options import OptionsIntelligence
from macro import MacroIntelligence
from risk_manager import RiskManager, Position
from sentiment import NewsSentimentEngine
from alerts import TelegramAlerts
from live_feeds import LiveDataHub
from telegram_cmd import TelegramCommander
from kill_switch import KillSwitch
from post_market import PostMarketAnalyzer
from safety import EventCalendar, SafeHours, SmartOrderRouter, Watchdog

Path(config.LOG_DIR).mkdir(exist_ok=True)
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(f"{config.LOG_DIR}/v6_{datetime.now():%Y%m%d}.log")])
logger = logging.getLogger("GXTradeIntel.V6")


class ConductorBot:
    def __init__(self):
        self.broker = get_broker()
        self.risk = RiskManager()
        self.options = OptionsIntelligence()
        self.news = NewsSentimentEngine()
        self.alerts = TelegramAlerts()
        self.live_data = LiveDataHub()
        self.telegram_cmd = TelegramCommander(bot_ref=self)
        self.kill_switch = KillSwitch()
        self.post_market = PostMarketAnalyzer()
        self.watchdog = Watchdog()
        self.event_calendar = EventCalendar()
        self.safe_hours = SafeHours()
        self.order_router = SmartOrderRouter()
        self.running = False
        self.active_engine = None
        self.conductor_decision = None
        self.last_news = None
        self.last_refresh = None
        self.last_live_refresh = None
        self.regime_data = {}

    def _interval(self):
        n = datetime.now().time()
        if config.GOLDEN_START <= n <= config.GOLDEN_END: return config.SCAN_INTERVAL_GOLDEN
        if config.DEAD_START <= n <= config.DEAD_END: return config.SCAN_INTERVAL_DEAD
        return config.SCAN_INTERVAL_NORMAL

    def _in_market(self):
        return config.SCAN_START <= datetime.now().time() <= config.SQUARE_OFF

    def pre_market(self) -> bool:
        logger.info("═" * 60)
        logger.info(f"  🎼 GX TRADEINTEL v6 | ₹{config.TOTAL_CAPITAL:,} | {'PAPER' if config.PAPER_TRADE else 'LIVE'} | {config.EXECUTION_MODE}")
        logger.info(f"  📅 {datetime.now():%A %d %B %Y} | Broker: {config.BROKER}")
        logger.info("═" * 60)

        # Crash recovery
        saved = StatePersistence.load_positions()
        if saved:
            for sp in saved:
                pos = Position(sp["symbol"], sp["token"], sp["direction"], sp["entry_price"],
                    sp["quantity"], sp["stop_loss"], sp["target_1"], sp["target_2"],
                    sp["order_id"], datetime.fromisoformat(sp["entry_time"]),
                    highest_premium=sp.get("highest_premium", sp["entry_price"]))
                self.risk.positions.append(pos)
                self.risk.record_trade()
            self.alerts.send(f"🔄 <b>RECOVERED</b> {len(saved)} position(s) from crash")

        good, reason = self.options.is_good_trading_day()
        logger.info(f"  📆 {reason}")

        if not self.broker.login():
            self.kill_switch.record_api_failure("Login failed"); return False
        self.kill_switch.record_api_success()
        self.last_refresh = datetime.now()
        self.broker.load_instruments()

        items = self.news.fetch_news()
        self.news.analyze_sentiment_batch(items)
        self.last_news = datetime.now()

        sentiment = self.news.get_market_sentiment_score()
        nifty = self.broker.get_nifty_ltp() or 0
        self.alerts.send_morning_briefing(nifty, sentiment, self.news.get_high_impact_news())

        logger.info("📡 Fetching live feeds...")
        self.live_data.fetch_all("NIFTY")
        self.last_live_refresh = datetime.now()
        self.alerts.send(self.live_data.get_summary_text())

        if self.live_data.vix > 0:
            self.kill_switch.check_market_abnormality(nifty, nifty, self.live_data.vix)

        self.telegram_cmd.start_listening()
        if not good:
            self.alerts.send(f"⏸️ <b>LIMITED TODAY</b>\n{reason}")
        return True

    def run_conductor(self):
        inst = config.INSTRUMENTS[config.PRIMARY_INSTRUMENT]
        df_15m = self.broker.get_historical_data(inst["exchange"], inst["token"], "FIFTEEN_MINUTE", 5)
        if df_15m.empty: return

        ind_cfg = {"supertrend_period": 10, "supertrend_multiplier": 3, "ema_trend": 50,
            "ema_fast": 9, "ema_slow": 21, "adx_period": 14, "rsi_period": 14,
            "bb_period": 20, "bb_std": 2.0, "obv_lookback": 10}
        df_15m = compute_all(df_15m, ind_cfg)
        vix = self.live_data.vix or 0
        self.regime_data = detect_regime(df_15m, vix)

        L = df_15m.iloc[-1]
        indicators = {"price": L["close"], "adx": L.get("adx", 0), "rsi": L.get("rsi", 50),
            "st_dir": L.get("st_direction", 0), "vs_vwap": L.get("price_vs_vwap", 0),
            "ema_cross": L.get("ema_cross", 0), "bb_expanding": L.get("bb_bw", 0) > 0.02,
            "vol_ratio": L.get("vol_ratio", 1), "atr_ratio": self.regime_data.get("atr_ratio", 1),
            "vwap_dev": ((L["close"] - L.get("vwap", L["close"])) / L.get("vwap", L["close"]) * 100) if L.get("vwap", 0) > 0 else 0}

        macro = {"vix": vix, "fii": self.live_data.fii_dii.get("fii_net", 0),
            "dii": self.live_data.fii_dii.get("dii_net", 0), "crude": self.live_data.crude}

        self.conductor_decision = call_conductor(indicators, self.regime_data, macro, self.news.get_market_sentiment_score())
        strategy = self.conductor_decision.get("strategy", "NO_TRADE")
        conf = self.conductor_decision.get("confidence", 0)

        if strategy != "NO_TRADE":
            self.active_engine = strategy
            emoji = {"MOMENTUM": "🚀", "MEAN_REVERSION": "📉", "SCALPER": "⚡"}.get(strategy, "❓")
            self.alerts.send(f"{emoji} <b>CONDUCTOR</b>: {strategy} ({conf}%) | Regime: {self.regime_data.get('regime')} | VIX: {vix:.1f}")
        else:
            self.active_engine = None
            self.alerts.send(f"⏸️ <b>NO TRADE</b> — {self.conductor_decision.get('reasoning', '')[:80]}")

    def scan_cycle(self):
        # Kill switch check EVERY cycle
        safe, reason = self.kill_switch.is_safe()
        if not safe:
            self.kill_switch.emergency_square_off(self.broker, self.risk.positions)
            self.running = False
            self.alerts.send(f"🛑 <b>KILL SWITCH</b>\n{reason}")
            return

        self.kill_switch.check_api_staleness()

        # Record alive after conductor/data fetch
        self.kill_switch.record_api_success()

        if self.last_refresh and (datetime.now() - self.last_refresh).seconds > config.SESSION_REFRESH:
            self.broker.refresh_session(); self.last_refresh = datetime.now(); self.kill_switch.record_api_success()

        if self.last_live_refresh and (datetime.now() - self.last_live_refresh).seconds > 600:
            try: self.live_data.fetch_all("NIFTY"); self.last_live_refresh = datetime.now()
            except: pass

        if self.last_news and (datetime.now() - self.last_news).seconds > config.NEWS_REFRESH:
            self.news.analyze_sentiment_batch(self.news.fetch_news()); self.last_news = datetime.now()
            if self.active_engine:
                ov = check_news_override(getattr(self.news, 'cached_news', []), self.active_engine, self.conductor_decision.get("direction", "NEUTRAL"))
                if ov.get("override"):
                    self.active_engine = ov["new_strategy"] if ov["new_strategy"] != "NO_TRADE" else None
                    self.alerts.send(f"📰 <b>NEWS OVERRIDE</b>\n{ov['reason']}")

        self._manage_positions()
        StatePersistence.save_positions(self.risk.positions)

        can, _ = self.risk.can_trade()
        if not can or not self.active_engine: return

        # Multi-instrument scan: check all active instruments, pick best signal
        multi = getattr(config, "MULTI_INSTRUMENT", {})
        if multi.get("enabled", False):
            best_signal = None
            best_instrument = None
            best_score = 0

            for inst_name in getattr(config, "ACTIVE_INSTRUMENTS", [config.PRIMARY_INSTRUMENT]):
                inst = config.INSTRUMENTS.get(inst_name)
                if not inst: continue

                try:
                    df_5m = self.broker.get_historical_data(inst["exchange"], inst["token"], "FIVE_MINUTE", 3)
                    self.kill_switch.record_api_success()
                except Exception:
                    continue
                if df_5m.empty: continue

                df_15m = pd.DataFrame()
                try:
                    df_15m = self.broker.get_historical_data(inst["exchange"], inst["token"], "FIFTEEN_MINUTE", 5)
                except Exception:
                    pass

                ns = self.news.get_market_sentiment_score().get("score", 0)
                signal = None
                if self.active_engine == "MOMENTUM": signal = momentum.generate(df_5m, df_15m if not df_15m.empty else None, ns)
                elif self.active_engine == "MEAN_REVERSION": signal = mean_reversion.generate(df_5m, df_15m if not df_15m.empty else None, ns)
                elif self.active_engine == "SCALPER": signal = scalper.generate(df_5m, df_15m if not df_15m.empty else None, ns)

                if signal and hasattr(signal, "confidence") and signal.confidence > best_score:
                    best_signal = signal
                    best_instrument = inst_name
                    best_score = signal.confidence

            signal = best_signal
            if best_instrument and best_instrument != config.PRIMARY_INSTRUMENT:
                logger.info(f"Multi-scan: Best setup on {best_instrument} (score {best_score})")
                self.alerts.send(f"🔍 Multi-scan: Best setup on <b>{best_instrument}</b> (score {best_score})")
        else:
            # Single instrument mode (original behavior)
            inst = config.INSTRUMENTS[config.PRIMARY_INSTRUMENT]
            try:
                df_5m = self.broker.get_historical_data(inst["exchange"], inst["token"], "FIVE_MINUTE", 3)
                df_15m = self.broker.get_historical_data(inst["exchange"], inst["token"], "FIFTEEN_MINUTE", 5)
                self.kill_switch.record_api_success()
            except Exception as e:
                self.kill_switch.record_api_failure(str(e)); return
            if df_5m.empty: return

            ns = self.news.get_market_sentiment_score().get("score", 0)
            signal = None
            if self.active_engine == "MOMENTUM": signal = momentum.generate(df_5m, df_15m if not df_15m.empty else None, ns)
            elif self.active_engine == "MEAN_REVERSION": signal = mean_reversion.generate(df_5m, df_15m if not df_15m.empty else None, ns)
            elif self.active_engine == "SCALPER": signal = scalper.generate(df_5m, df_15m if not df_15m.empty else None, ns)

        if not signal: return

        if signal.is_tradeable:
            logger.info(f"🎯 [{signal.engine}] {signal.action} | {signal.confidence}% | ₹{signal.entry_price:,.2f}")
            for r in signal.reasons: logger.info(f"   → {r}")
        self._log_signal(signal)

        if signal.is_tradeable:
            if config.EXECUTION_MODE == "AUTO":
                self._execute(signal)
            else:
                self.alerts.send_signal(signal)
                self.alerts.send("☝️ <b>SUGGEST MODE</b> — You decide.")

    def _execute(self, signal):
        safe, _ = self.kill_switch.is_safe()
        if not safe: return
        can, _ = self.risk.can_trade()
        if not can: return

        contract = self.broker.find_atm_option(config.PRIMARY_INSTRUMENT, signal.entry_price, signal.option_type, 0)
        if not contract: return
        premium = self.broker.get_ltp("NFO", contract["symbol"], contract["token"])
        if not premium: return
        valid, _ = self.options.validate_option(premium)
        if not valid: return

        vix_mult = 0.5 if self.live_data.vix > config.MACRO.get("vix_reduce_size_above", 25) else 1.0
        qty, cost, sr = self.risk.calculate_position_size(premium, contract["lot_size"], vix_mult)
        if qty == 0: return

        sane, _ = self.kill_switch.check_order_sanity("BUY", qty, premium)
        if not sane: return

        self.alerts.send_signal(signal)
        opt_sl = round(premium * (1 - config.STOP_LOSS_PCT / 100), 2)
        opt_t1 = round(premium * (1 + config.PROFIT_TARGET_1_PCT / 100), 2)
        opt_t2 = round(premium * (1 + config.PROFIT_TARGET_2_PCT / 100), 2)

        result = OrderConfirmation.place_with_retry(self.broker, 3, symbol=contract["symbol"], token=contract["token"],
            transaction_type="BUY", quantity=qty, order_type="MARKET", product_type="INTRADAY")

        if not result or result.get("status") != "FILLED":
            self.kill_switch.record_api_failure("Order not filled")
            self.alerts.send(f"❌ <b>ORDER FAILED</b>"); return

        self.kill_switch.record_api_success()
        pos = Position(contract["symbol"], contract["token"], signal.action, premium, qty,
            opt_sl, opt_t1, opt_t2, result["order_id"], datetime.now(), highest_premium=premium)
        self.risk.positions.append(pos)
        self.risk.record_trade()
        StatePersistence.save_positions(self.risk.positions)
        self.alerts.send_trade_entry(contract["symbol"], f"[{signal.engine}] {signal.action}", qty, premium, result["order_id"])

    def _manage_positions(self):
        for pos in self.risk.positions:
            if not pos.is_open: continue
            try:
                cur = self.broker.get_ltp("NFO", pos.symbol, pos.token)
                self.kill_switch.record_api_success()
            except Exception as e:
                self.kill_switch.record_api_failure(str(e)); continue
            if not cur: continue
            should, reason = self.risk.check_exit(pos, cur)
            if should:
                OrderConfirmation.place_with_retry(self.broker, 3, symbol=pos.symbol, token=pos.token,
                    transaction_type="SELL", quantity=pos.quantity, order_type="MARKET", product_type="INTRADAY")
                self.risk.record_exit(pos, cur, reason)
                self.alerts.send_trade_exit(pos.symbol, pos.entry_price, cur, pos.quantity, pos.pnl)
                self._log_trade(pos)
                StatePersistence.save_positions(self.risk.positions)

    def _post_market(self):
        inst = config.INSTRUMENTS[config.PRIMARY_INSTRUMENT]
        df_d = self.broker.get_historical_data(inst["exchange"], inst["token"], "ONE_DAY", 5)
        regime_result = self.post_market.validate_regime(self.regime_data.get("regime", "UNKNOWN"), df_d)
        metrics = {}
        if os.path.exists(f"{config.LOG_DIR}/trades.csv"):
            import pandas as pd
            try:
                df_t = pd.read_csv(f"{config.LOG_DIR}/trades.csv")
                metrics = self.post_market.calculate_full_metrics([{"pnl": r.get("pnl", 0)} for _, r in df_t.iterrows()])
            except: pass
        stats = self.risk.daily_stats()
        self.post_market.log_equity(datetime.now().strftime("%Y-%m-%d"), config.TOTAL_CAPITAL + stats["pnl"], stats["pnl"])
        self.alerts.send(self.post_market.generate_report_card(regime_result, stats, metrics))
        StatePersistence.save_bot_state(self.regime_data.get("regime", ""), self.active_engine or "NONE", stats["pnl"], stats["trades"])

    def run(self):
        self.running = True
        try:
            if not self.pre_market(): return
            while datetime.now().time() < config.SCAN_START and self.running:
                if datetime.now().time() >= config.MARKET_CLOSE: break
                t_.sleep(15)

            self.run_conductor()
            rechecked = set()
            while self._in_market() and self.running:
                try:
                    for rt in config.CONDUCTOR.get("recheck_at", []):
                        k = rt.strftime("%H%M")
                        if datetime.now().time() >= rt and k not in rechecked:
                            self.run_conductor(); rechecked.add(k)
                    self.scan_cycle()
                    t_.sleep(self._interval())
                except KeyboardInterrupt: raise
                except Exception as e: logger.error(f"Error: {e}", exc_info=True); t_.sleep(30)

            # Square off
            for pos in self.risk.positions:
                if pos.is_open:
                    p = self.broker.get_ltp("NFO", pos.symbol, pos.token)
                    if p:
                        OrderConfirmation.place_with_retry(self.broker, 3, symbol=pos.symbol, token=pos.token,
                            transaction_type="SELL", quantity=pos.quantity, order_type="MARKET", product_type="INTRADAY")
                        self.risk.record_exit(pos, p, "END_OF_DAY")
                        self.alerts.send_trade_exit(pos.symbol, pos.entry_price, p, pos.quantity, pos.pnl)
                        self._log_trade(pos)

            stats = self.risk.daily_stats()
            self.alerts.send_daily_summary(stats["trades"], stats["wins"], stats["losses"], stats["pnl"])
            self._post_market()
            StatePersistence.clear_state()
        except KeyboardInterrupt:
            StatePersistence.save_positions(self.risk.positions)
        finally:
            self.telegram_cmd.stop_listening(); self.broker.logout(); self.running = False

    def _log_signal(self, s):
        p = f"{config.LOG_DIR}/signals.csv"; e = os.path.exists(p)
        with open(p, "a", newline="") as f:
            w = csv.writer(f)
            if not e: w.writerow(["time","engine","action","confidence","entry","sl","t1","rr","instrument","reasons"])
            w.writerow([datetime.now().isoformat(),s.engine,s.action,s.confidence,s.entry_price,s.stop_loss,s.target_1,s.risk_reward,s.instrument,"|".join(s.reasons[:5])])

    def _log_trade(self, p):
        path = f"{config.LOG_DIR}/trades.csv"; e = os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if not e: w.writerow(["entry_time","exit_time","symbol","dir","entry","exit","qty","pnl","reason","min","engine"])
            w.writerow([p.entry_time.isoformat(),p.exit_time.isoformat() if p.exit_time else "",p.symbol,p.direction,p.entry_price,p.exit_price,p.quantity,round(p.pnl,2),p.exit_reason,p.holding_minutes,self.active_engine or ""])

if __name__ == "__main__":
    ConductorBot().run()
