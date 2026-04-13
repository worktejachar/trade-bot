# -*- coding: utf-8 -*-
"""
GX TradeIntel v4 — Macro Intelligence
========================================
Source: market-microstructure-india (full skill)
Analyzes: FII/DII flows, India VIX, crude oil, rupee, gap opens
"""
import logging
import config

logger = logging.getLogger("GXTradeIntel.Macro")


class MacroIntelligence:
    """Market microstructure analysis — the big picture."""

    # ── FII/DII Flow [microstructure §1] ──

    @staticmethod
    def analyze_fii_dii(fii_flow_cr: float, dii_flow_cr: float) -> dict:
        m = config.MACRO
        fii_abs = abs(fii_flow_cr)

        # Magnitude
        if fii_abs < m["fii_negligible_cr"]:
            magnitude = "NEGLIGIBLE"
        elif fii_abs < m["fii_moderate_cr"]:
            magnitude = "MODERATE"
        elif fii_abs < m["fii_significant_cr"]:
            magnitude = "SIGNIFICANT"
        else:
            magnitude = "MAJOR"

        # Direction matrix
        fii_buy = fii_flow_cr > 0
        dii_buy = dii_flow_cr > 0

        if fii_buy and dii_buy:
            bias, desc = "STRONG_BULL", "Both FII+DII buying — rare, powerful"
        elif fii_buy and not dii_buy:
            bias, desc = "BULL", "FII driving, DII booking profits"
        elif not fii_buy and dii_buy:
            bias, desc = "RANGE", "FII selling vs DII buying — tug of war"
        else:
            bias, desc = "STRONG_BEAR", "Both FII+DII selling — panic"

        return {
            "fii": fii_flow_cr, "dii": dii_flow_cr,
            "magnitude": magnitude, "bias": bias, "description": desc,
            "nifty_impact_est": f"{'+'if fii_buy else '-'}{50 if magnitude=='MODERATE' else 150 if magnitude=='SIGNIFICANT' else 300 if magnitude=='MAJOR' else 0} pts",
        }

    # ── India VIX [microstructure §2] ──

    @staticmethod
    def analyze_vix(vix_value: float) -> dict:
        m = config.MACRO

        if vix_value < m["vix_low"]:
            zone, action = "EXTREME_LOW", "Complacent — big move coming, be cautious"
        elif vix_value < m["vix_normal_low"]:
            zone, action = "LOW", "Good for directional trades"
        elif vix_value < m["vix_normal_high"]:
            zone, action = "NORMAL", "Standard conditions"
        elif vix_value < m["vix_elevated"]:
            zone, action = "ELEVATED", "Wider SL needed, reduce size"
        elif vix_value < m["vix_panic"]:
            zone, action = "HIGH", "Market scared — potential bottom forming"
        else:
            zone, action = "PANIC", "Extreme fear — contrarian buy zone (risky)"

        # Position size adjustment
        size_multiplier = 1.0
        if vix_value > m["vix_reduce_size_above"]:
            size_multiplier = 0.5  # Halve position when VIX high

        # Options impact
        options_note = "Options expensive (high IV)" if vix_value > m["vix_normal_high"] else "Options reasonably priced"

        return {
            "vix": vix_value, "zone": zone, "action": action,
            "size_multiplier": size_multiplier, "options_note": options_note,
        }

    # ── Crude Oil [microstructure §3] ──

    @staticmethod
    def analyze_crude(brent_price: float) -> dict:
        m = config.MACRO

        if brent_price < m["crude_positive_below"]:
            impact, bias = "POSITIVE", "Low inflation, strong rupee — bullish India"
        elif brent_price < m["crude_neutral_below"]:
            impact, bias = "NEUTRAL", "Manageable for India"
        elif brent_price < m["crude_cautionary_below"]:
            impact, bias = "CAUTIONARY", "Inflation pressure building"
        else:
            impact, bias = "BEARISH", "High crude = margin compression, FII outflows"

        sectors = []
        if brent_price > m["crude_cautionary_below"]:
            sectors = ["BEARISH: OMCs, Airlines, Paints", "BULLISH: ONGC, Oil India, Vedanta"]
        elif brent_price < m["crude_positive_below"]:
            sectors = ["BULLISH: Auto, Aviation, Paints", "NEUTRAL: Oil explorers"]

        return {"crude": brent_price, "impact": impact, "bias": bias, "sector_impact": sectors}

    # ── Gap Analysis [price-action-patterns §2 + microstructure §5] ──

    @staticmethod
    def analyze_gap_open(current_open: float, prev_close: float) -> dict:
        m = config.MACRO
        gap = current_open - prev_close
        gap_pct = abs(gap) / prev_close * 100
        direction = "UP" if gap > 0 else "DOWN" if gap < 0 else "FLAT"

        if gap_pct < 0.1:
            return {"type": "FLAT", "pct": 0, "strategy": "Wait for first 15-min candle", "fill_prob": 0}

        if gap_pct > m["gap_full_pct"]:
            fill_prob = m["gap_fill_prob_full"]
            strategy = f"Gap-and-go likely — DON'T fade, wait for pullback" if direction == "UP" else "Gap-and-go down — don't buy dip yet"
        elif gap_pct > m["gap_small_pct"]:
            fill_prob = m["gap_fill_prob_partial"]
            strategy = "Partial gap — may fill 50%, watch first 30 min"
        else:
            fill_prob = m["gap_fill_prob_small"]
            strategy = "Small gap — likely to fill within first hour"

        return {
            "type": f"GAP_{direction}", "pct": round(gap_pct, 2), "points": round(gap, 1),
            "fill_prob": fill_prob, "strategy": strategy,
        }

    # ── Aggregate Macro Score ──

    @staticmethod
    def macro_bias_score(fii_dii: dict = None, vix: dict = None, crude: dict = None) -> dict:
        """Combine all macro factors into a single bias score (-100 to +100)."""
        score = 0
        reasons = []

        if fii_dii:
            flow_map = {"STRONG_BULL": 30, "BULL": 15, "RANGE": 0, "STRONG_BEAR": -30}
            s = flow_map.get(fii_dii["bias"], 0)
            score += s
            if s != 0:
                reasons.append(f"FII/DII: {fii_dii['bias']} ({s:+d})")

        if vix:
            if vix["zone"] in ("PANIC", "HIGH"):
                score -= 15
                reasons.append(f"VIX {vix['vix']:.1f} ({vix['zone']}) → Risk-off (-15)")
            elif vix["zone"] == "LOW":
                score += 10
                reasons.append(f"VIX {vix['vix']:.1f} (low) → Favorable (+10)")

        if crude:
            crude_map = {"POSITIVE": 15, "NEUTRAL": 0, "CAUTIONARY": -10, "BEARISH": -20}
            s = crude_map.get(crude["impact"], 0)
            score += s
            if s != 0:
                reasons.append(f"Crude ${crude['crude']:.0f}: {crude['impact']} ({s:+d})")

        label = "BULLISH" if score > 15 else "BEARISH" if score < -15 else "NEUTRAL"
        return {"score": score, "label": label, "reasons": reasons}
