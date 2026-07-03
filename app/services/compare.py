"""Multi-ticker comparison: ranking + analyst verdict.

Deterministic by default. Takes a list of per-ticker AnalysisResponse objects,
ranks them by composite score, and writes a senior-analyst verdict on which name
deserves the most attention today and why.
"""
from __future__ import annotations
from datetime import datetime, timezone

from app.models import AnalysisResponse, CompareResponse, RankedItem

DIMS = ["growth", "profitability", "moat", "valuation", "debt", "momentum", "risk"]
DIM_LABELS = {
    "growth": "growth", "profitability": "profitability", "moat": "moat",
    "valuation": "valuation", "debt": "balance sheet", "momentum": "momentum",
    "risk": "low risk profile",
}


def _top_dims(scores, n=2):
    vals = {d: getattr(scores, d) for d in DIMS}
    ranked = sorted(vals.items(), key=lambda kv: kv[1], reverse=True)
    return [DIM_LABELS[d] for d, _ in ranked[:n]]


def _weakest_dim(scores):
    vals = {d: getattr(scores, d) for d in DIMS}
    d = min(vals.items(), key=lambda kv: kv[1])[0]
    return DIM_LABELS[d]


def _verdict(ranked: list[AnalysisResponse]) -> str:
    leader = ranked[0]
    lf, ls = leader.fundamentals, leader.scores
    strengths = " and ".join(_top_dims(ls))
    parts = [
        f"Across {len(ranked)} companies, {lf.name or lf.ticker} ({lf.ticker}) leads "
        f"with a composite of {ls.composite:.0f}/100 ({ls.rating}), carried by its "
        f"{strengths}."
    ]

    if len(ranked) > 1:
        runner = ranked[1]
        rf, rs = runner.fundamentals, runner.scores
        gap = ls.composite - rs.composite
        if gap <= 4:
            parts.append(
                f"It is a close call: {rf.ticker} trails by just {gap:.0f} points "
                f"({rs.composite:.0f}), so conviction here is moderate."
            )
        else:
            parts.append(
                f"It is a clear {gap:.0f}-point lead over {rf.ticker} ({rs.composite:.0f}), "
                f"whose relative soft spot is {_weakest_dim(rs)}."
            )

    laggard = ranked[-1]
    if laggard is not leader:
        gf, gs = laggard.fundamentals, laggard.scores
        parts.append(
            f"{gf.ticker} closes the field ({gs.composite:.0f}, {gs.rating}), "
            f"held back by its {_weakest_dim(gs)}."
        )

    # Attention call: leader, unless a high-conviction name screens notably cheap.
    cheap = [a for a in ranked if a.scores.valuation >= 70 and a.scores.rating in ("Strong Buy", "Buy")]
    if cheap and cheap[0] is not leader:
        c = cheap[0]
        parts.append(
            f"Worth a second look: {c.fundamentals.ticker} pairs a {c.scores.rating} "
            f"rating with the most attractive valuation of the group "
            f"(valuation score {c.scores.valuation:.0f})."
        )

    parts.append(
        f"Bottom line: {lf.ticker} deserves the most attention today on the strongest "
        f"risk-adjusted profile. Research commentary, not personalised advice."
    )
    return " ".join(parts)


def build_comparison(items: list[AnalysisResponse], errors: list[str]) -> CompareResponse:
    ranked = sorted(items, key=lambda a: a.scores.composite, reverse=True)
    leaderboard = [
        RankedItem(
            rank=i + 1,
            ticker=a.fundamentals.ticker,
            name=a.fundamentals.name,
            composite=a.scores.composite,
            rating=a.scores.rating,
        )
        for i, a in enumerate(ranked)
    ]
    return CompareResponse(
        items=ranked,
        ranking=leaderboard,
        top_pick=ranked[0].fundamentals.ticker if ranked else "",
        verdict=_verdict(ranked) if ranked else "No companies could be analyzed.",
        errors=errors,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
