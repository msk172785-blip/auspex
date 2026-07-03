"""Proprietary scoring engine.

Each dimension is scored 0-100 from fundamentals, then combined into a weighted
composite. Scoring is transparent and deterministic: every sub-score maps a raw
metric onto a 0-100 scale via piecewise-linear thresholds. This is intentionally
simple for the V0 demo and easy to tune later.

Weights (sum = 100%):
    growth         20%
    profitability  18%
    moat           15%
    valuation      15%
    debt           12%
    momentum       12%
    risk            8%
"""
from __future__ import annotations
from typing import Optional

from app.models import Fundamentals, ScoreBreakdown

WEIGHTS = {
    "growth": 0.20,
    "profitability": 0.18,
    "moat": 0.15,
    "valuation": 0.15,
    "debt": 0.12,
    "momentum": 0.12,
    "risk": 0.08,
}


def _scale(value: Optional[float], low: float, high: float,
           invert: bool = False, neutral: float = 50.0) -> float:
    """Map value onto 0-100. value<=low -> 0, value>=high -> 100 (or inverted)."""
    if value is None:
        return neutral
    if high == low:
        return neutral
    pct = (value - low) / (high - low)
    pct = max(0.0, min(1.0, pct))
    score = pct * 100.0
    return 100.0 - score if invert else score


def _growth_score(f: Fundamentals) -> float:
    rev = _scale(f.revenue_growth, 0.0, 0.40)        # 0% -> 0, 40%+ -> 100
    eps = _scale(f.earnings_growth, -0.10, 0.50)     # -10% -> 0, 50%+ -> 100
    return round(0.6 * rev + 0.4 * eps, 1)


def _profitability_score(f: Fundamentals) -> float:
    op = _scale(f.operating_margin, 0.0, 0.40)
    net = _scale(f.profit_margin, 0.0, 0.30)
    roe = _scale(f.roe, 0.0, 0.40)
    return round(0.4 * op + 0.3 * net + 0.3 * roe, 1)


def _moat_score(f: Fundamentals) -> float:
    # Wide moats tend to show in durable gross margins and high returns on equity.
    gm = _scale(f.gross_margin, 0.20, 0.75)
    roe = _scale(f.roe, 0.10, 0.50)
    op = _scale(f.operating_margin, 0.05, 0.40)
    return round(0.45 * gm + 0.30 * roe + 0.25 * op, 1)


def _valuation_score(f: Fundamentals) -> float:
    # Cheaper = higher score. Blend forward P/E, P/S and PEG.
    pe = _scale(f.pe_forward or f.pe_trailing, 10.0, 60.0, invert=True)
    ps = _scale(f.price_to_sales, 1.0, 25.0, invert=True)
    peg = _scale(f.peg, 0.5, 3.5, invert=True)
    return round(0.45 * pe + 0.25 * ps + 0.30 * peg, 1)


def _debt_score(f: Fundamentals) -> float:
    # debt_to_equity is yfinance-style percent (e.g. 45 means 0.45x).
    de = _scale(f.debt_to_equity, 10.0, 200.0, invert=True)
    # Net cash position is a bonus.
    net_cash_bonus = 0.0
    if f.total_cash is not None and f.total_debt is not None:
        if f.total_cash > f.total_debt:
            net_cash_bonus = 15.0
    return round(min(100.0, de + net_cash_bonus), 1)


def _momentum_score(f: Fundamentals) -> float:
    # Where does price sit within the 52-week range? Mid-to-upper is constructive.
    if f.price is None or f.week52_high is None or f.week52_low is None:
        return 50.0
    if f.week52_high == f.week52_low:
        return 50.0
    pos = (f.price - f.week52_low) / (f.week52_high - f.week52_low)
    pos = max(0.0, min(1.0, pos))
    # Reward 55-90% of range most; penalise extremes (overbought / broken).
    if pos < 0.5:
        return round(40.0 + pos * 60.0, 1)        # 0.0->40, 0.5->70
    if pos <= 0.9:
        return round(70.0 + (pos - 0.5) * 75.0, 1)  # 0.5->70, 0.9->100
    return round(100.0 - (pos - 0.9) * 200.0, 1)    # 0.9->100, 1.0->80


def _risk_score(f: Fundamentals) -> float:
    # Higher score = lower risk. Driven mainly by beta.
    beta = _scale(f.beta, 0.5, 2.5, invert=True, neutral=50.0)
    return round(beta, 1)


def _rating(composite: float) -> str:
    if composite >= 80:
        return "Strong Buy"
    if composite >= 67:
        return "Buy"
    if composite >= 50:
        return "Hold"
    if composite >= 38:
        return "Reduce"
    return "Sell"


def _confidence(f: Fundamentals) -> str:
    fields = [f.revenue_growth, f.earnings_growth, f.operating_margin,
              f.profit_margin, f.roe, f.gross_margin, f.pe_forward,
              f.debt_to_equity, f.beta, f.price_to_sales]
    present = sum(1 for x in fields if x is not None)
    ratio = present / len(fields)
    if ratio >= 0.8:
        return "High"
    if ratio >= 0.5:
        return "Medium"
    return "Low"


def compute_scores(f: Fundamentals) -> ScoreBreakdown:
    parts = {
        "growth": _growth_score(f),
        "profitability": _profitability_score(f),
        "moat": _moat_score(f),
        "valuation": _valuation_score(f),
        "debt": _debt_score(f),
        "momentum": _momentum_score(f),
        "risk": _risk_score(f),
    }
    composite = round(sum(parts[k] * WEIGHTS[k] for k in parts), 1)
    return ScoreBreakdown(
        **parts,
        composite=composite,
        rating=_rating(composite),
        confidence=_confidence(f),
    )
