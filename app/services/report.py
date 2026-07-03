"""Analyst report generator.

Builds a structured, senior-analyst-style report from fundamentals + scores.
Deterministic by default; if an LLM key is configured the executive summary and
conclusion are rewritten for a more natural voice.
"""
from __future__ import annotations
from typing import Optional
import json

from app.models import Fundamentals, ScoreBreakdown, NewsItem, Report
from app.config import settings
from app.services import llm


# ---------- formatting helpers ----------

def fmt_money(v: Optional[float], currency: str = "USD") -> str:
    if v is None:
        return "n/a"
    sign = "-" if v < 0 else ""
    v = abs(v)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= div:
            return f"{sign}{v / div:.2f}{unit}"
    return f"{sign}{v:.0f}"


def fmt_pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def fmt_num(v: Optional[float], suffix: str = "") -> str:
    return "n/a" if v is None else f"{v:.1f}{suffix}"


# ---------- narrative building ----------

def _bull_case(f: Fundamentals, s: ScoreBreakdown) -> list[str]:
    out = []
    if f.revenue_growth and f.revenue_growth >= 0.15:
        out.append(f"Revenue growing {fmt_pct(f.revenue_growth)} year-over-year, well above market average.")
    if f.gross_margin and f.gross_margin >= 0.5:
        out.append(f"Gross margin of {fmt_pct(f.gross_margin)} points to strong pricing power and a durable moat.")
    if f.roe and f.roe >= 0.25:
        out.append(f"Return on equity of {fmt_pct(f.roe)} reflects highly efficient capital allocation.")
    if f.free_cash_flow and f.free_cash_flow > 0:
        out.append(f"Generates {fmt_money(f.free_cash_flow, f.currency)} of free cash flow, funding growth without dilution.")
    if f.total_cash and f.total_debt and f.total_cash > f.total_debt:
        out.append("Net cash balance sheet provides resilience and optionality.")
    if s.moat >= 70:
        out.append("Moat indicators (margins, returns) screen in the top tier of the sector.")
    if not out:
        out.append("Fundamentals are stable; the investment case rests on execution rather than acceleration.")
    return out[:5]


def _bear_case(f: Fundamentals, s: ScoreBreakdown) -> list[str]:
    out = []
    if s.valuation <= 40:
        out.append(f"Valuation is demanding (fwd P/E {fmt_num(f.pe_forward)}, P/S {fmt_num(f.price_to_sales)}); much of the growth is already priced in.")
    if f.earnings_growth is not None and f.earnings_growth < 0:
        out.append(f"Earnings contracted {fmt_pct(f.earnings_growth)} year-over-year, signalling pressure on the model.")
    if f.debt_to_equity and f.debt_to_equity > 120:
        out.append(f"Debt-to-equity of {fmt_num(f.debt_to_equity)} adds financial leverage risk if rates stay high.")
    if f.beta and f.beta > 1.6:
        out.append(f"High beta ({fmt_num(f.beta)}) means outsized drawdowns in risk-off markets.")
    if f.profit_margin is not None and f.profit_margin < 0.08:
        out.append(f"Thin net margin ({fmt_pct(f.profit_margin)}) leaves little cushion against cost shocks.")
    if not out:
        out.append("No acute red flags in the data; the main risk is multiple compression from elevated expectations.")
    return out[:5]


def _what_changed(news: list[NewsItem]) -> list[str]:
    if not news:
        return ["No fresh catalysts detected in the latest news pull."]
    return [n.title for n in news[:4]]


def _competitive_position(f: Fundamentals, s: ScoreBreakdown) -> str:
    moat_word = "wide" if s.moat >= 70 else "narrow" if s.moat >= 45 else "limited"
    return (
        f"{f.name or f.ticker} operates in {f.industry or 'its industry'} "
        f"({f.sector or 'n/a'} sector). Margin structure and returns on capital imply a "
        f"{moat_word} competitive moat (moat score {s.moat:.0f}/100). "
        f"Gross margin of {fmt_pct(f.gross_margin)} and operating margin of "
        f"{fmt_pct(f.operating_margin)} are the clearest evidence of relative pricing power."
    )


def _valuation_text(f: Fundamentals, s: ScoreBreakdown) -> str:
    verdict = "rich" if s.valuation <= 40 else "fair" if s.valuation <= 65 else "attractive"
    return (
        f"On a forward P/E of {fmt_num(f.pe_forward)} (trailing {fmt_num(f.pe_trailing)}), "
        f"price-to-sales of {fmt_num(f.price_to_sales)} and PEG of {fmt_num(f.peg)}, "
        f"the valuation screens as {verdict} relative to the growth profile "
        f"(valuation score {s.valuation:.0f}/100). Market cap stands at "
        f"{fmt_money(f.market_cap, f.currency)}."
    )


def _risks(f: Fundamentals, s: ScoreBreakdown) -> list[str]:
    out = []
    if f.beta and f.beta > 1.3:
        out.append(f"Market risk: beta {fmt_num(f.beta)} amplifies index moves.")
    if s.valuation <= 45:
        out.append("Valuation risk: limited margin of safety if growth decelerates.")
    if f.debt_to_equity and f.debt_to_equity > 100:
        out.append("Balance-sheet risk: elevated leverage.")
    if f.industry and "Semiconduc" in f.industry:
        out.append("Cyclicality risk: semiconductor demand is historically cyclical.")
    out.append("Execution and competitive risk inherent to the sector.")
    return out[:5]


def _exec_summary(f: Fundamentals, s: ScoreBreakdown) -> str:
    return (
        f"{f.name or f.ticker} scores {s.composite:.0f}/100 on our composite model "
        f"({s.rating}). The setup pairs growth ({s.growth:.0f}) and profitability "
        f"({s.profitability:.0f}) against a valuation read of {s.valuation:.0f}. "
        f"At {fmt_money(f.market_cap, f.currency)} market cap and a forward P/E of "
        f"{fmt_num(f.pe_forward)}, the stock is a {s.rating.lower()} candidate for "
        f"investors comfortable with the sector's risk profile."
    )


def _conclusion(f: Fundamentals, s: ScoreBreakdown) -> str:
    lean = {
        "Strong Buy": "We see a compelling risk/reward.",
        "Buy": "The balance of evidence tilts positive.",
        "Hold": "We would wait for a better entry or clearer catalyst.",
        "Reduce": "We would trim into strength.",
        "Sell": "Risks outweigh the reward at current levels.",
    }.get(s.rating, "")
    return (
        f"Composite {s.composite:.0f}/100 ({s.rating}, {s.confidence.lower()} data confidence). "
        f"Strengths cluster in {'growth' if s.growth >= s.valuation else 'business quality'}; "
        f"the principal watch-item is {'valuation' if s.valuation < 50 else 'sustaining momentum'}. "
        f"{lean} This is research commentary, not personalised investment advice."
    )


def _maybe_llm(f: Fundamentals, s: ScoreBreakdown, base_summary: str, base_conclusion: str):
    if not settings.llm_enabled:
        return base_summary, base_conclusion, "template"
    payload = {
        "ticker": f.ticker,
        "name": f.name,
        "scores": s.model_dump(),
        "metrics": {
            "market_cap": f.market_cap, "pe_forward": f.pe_forward,
            "revenue_growth": f.revenue_growth, "profit_margin": f.profit_margin,
            "roe": f.roe, "gross_margin": f.gross_margin, "beta": f.beta,
        },
    }
    prompt = (
        "Using only the JSON below, write (1) a tight executive summary of under "
        "90 words and (2) a 3-4 sentence senior-analyst conclusion. Return strict "
        "JSON: {\"summary\": \"...\", \"conclusion\": \"...\"}. Be balanced, no hype, "
        "no personalised advice.\n\n" + json.dumps(payload)
    )
    raw = llm.enhance(prompt)
    if not raw:
        return base_summary, base_conclusion, "template"
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start:end + 1])
        return (
            parsed.get("summary", base_summary).strip(),
            parsed.get("conclusion", base_conclusion).strip(),
            f"llm:{settings.llm_provider}",
        )
    except Exception:
        return base_summary, base_conclusion, "template"


def build_report(f: Fundamentals, s: ScoreBreakdown, news: list[NewsItem]) -> Report:
    base_summary = _exec_summary(f, s)
    base_conclusion = _conclusion(f, s)
    summary, conclusion, generated_by = _maybe_llm(f, s, base_summary, base_conclusion)

    return Report(
        executive_summary=summary,
        bull_case=_bull_case(f, s),
        bear_case=_bear_case(f, s),
        what_changed=_what_changed(news),
        competitive_position=_competitive_position(f, s),
        valuation=_valuation_text(f, s),
        risks=_risks(f, s),
        final_score=s.composite,
        analyst_conclusion=conclusion,
        generated_by=generated_by,
    )
