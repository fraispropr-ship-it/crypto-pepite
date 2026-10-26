"""Radar Alt V2: independent confirmation and position-sizing guards.

All inputs are CLOSED candles; no market-data or network calls in this module.
Experimental filters. Passing them is not evidence of profitability.
"""
import math

MAX_H1_ATR = 1.8
MIN_CLOSE_POSITION = 0.65
MAX_BREAKOUT_ATR_H1 = 0.8
MIN_M15_CLOSE_POSITION = 0.60
MAX_LEVERAGE = 10
MAX_FEE_R = 0.15


def confirm_breakout(h1, m15, level, atr_h1, candle_end_ms):
    """Require H1 breakout quality and the final closed M15 to confirm.

    Returns (accepted, reason). No data -> fail closed.
    DataFrames have t,o,h,l,c fields and timestamps in milliseconds.
    """
    if h1 is None or len(h1) < 2 or m15 is None or len(m15) < 4:
        return False, "données H1/M15 insuffisantes"
    if not math.isfinite(atr_h1) or atr_h1 <= 0 or level <= 0:
        return False, "ATR/niveau invalide"
    x = h1.iloc[-1]
    if int(x.t) + 3_600_000 != int(candle_end_ms):
        return False, "H1 non synchronisée"
    if not (x.c > level and x.c > x.o):
        return False, "pas de cassure H1 haussière"
    spread = float(x.h - x.l)
    if spread <= 0 or spread / atr_h1 > MAX_H1_ATR:
        return False, "bougie H1 trop étendue"
    if (float(x.c - x.l) / spread) < MIN_CLOSE_POSITION:
        return False, "clôture H1 trop basse"
    if (float(x.c) - level) / atr_h1 > MAX_BREAKOUT_ATR_H1:
        return False, "cassure H1 déjà trop éloignée"
    start = int(x.t)
    last_four = m15[(m15.t >= start) & (m15.t < start + 3_600_000)].sort_values("t")
    if len(last_four) != 4 or list(last_four.t.astype(int)) != [start + k * 900_000 for k in range(4)]:
        return False, "séquence M15 incomplète"
    last = last_four.iloc[-1]
    rng = float(last.h - last.l)
    if rng <= 0 or not (last.c > last.o and last.c > level):
        return False, "M15 finale non confirmée"
    if (float(last.c - last.l) / rng) < MIN_M15_CLOSE_POSITION:
        return False, "clôture M15 trop basse"
    return True, "cassure H1 et confirmation M15"


def guarded_sizing(entry, stop, qty_step, min_qty, tick, risk_usdt=1.0, margin_limit=20.0,
                   leverage_limit=MAX_LEVERAGE, fee_rate=0.0006):
    """Size for <=risk USDT INCLUDING estimated round-trip taker fees.

    Never exceed max leverage; reject instead of raising leverage to meet margin.
    """
    nums = (entry, stop, qty_step, min_qty, tick, risk_usdt, margin_limit, leverage_limit, fee_rate)
    if not all(math.isfinite(float(v)) for v in nums):
        return None, "valeurs non finies"
    if not (entry > stop > 0 and qty_step > 0 and tick > 0 and risk_usdt > 0
            and margin_limit > 0 and leverage_limit >= 1 and fee_rate >= 0):
        return None, "paramètres risque invalides"
    distance = entry - stop
    fee_per_unit = fee_rate * (entry + stop)
    if fee_per_unit / distance > MAX_FEE_R:
        return None, "frais trop élevés par rapport au stop"
    max_qty_risk = risk_usdt / (distance + fee_per_unit)
    max_qty_margin = margin_limit * leverage_limit / entry
    qty = math.floor(min(max_qty_risk, max_qty_margin) / qty_step + 1e-10) * qty_step
    qty = round(qty, 12)
    if qty <= 0 or qty < min_qty:
        return None, "quantité sous minimum Zoomex"
    notional = qty * entry
    leverage = max(1, math.ceil(notional / margin_limit))
    if leverage > leverage_limit:
        return None, "levier maximum dépassé"
    return dict(q=qty, notional=notional, lev=leverage, marge=notional / leverage,
                risque_usdt=qty * (distance + fee_per_unit),
                frais_R=fee_per_unit / distance), "ok"
