"""Expressions de dates logiques, évaluées de façon déterministe.

Une date dont la base est conditionnelle n'est JAMAIS rendue absolue tant qu'une variable manque :
  max(2026-12-16, notification_date)  -> {value: None, earliest: 2026-12-16, missing: [notification_date]}
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from ..calculations import add_days, add_months, fmt_date

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def evaluate(expr: str, env: dict[str, Optional[date]]) -> dict:
    """expr : 'YYYY-MM-DD' | 'var' | 'max(a, b)' | 'one_of(a, b)'."""
    expr = expr.strip()
    m = re.fullmatch(r"(max|one_of)\((.+)\)", expr)
    if m:
        args = [a.strip() for a in m.group(2).split(",")]
        vals, missing = [], []
        for a in args:
            if _ISO.fullmatch(a):
                vals.append(date.fromisoformat(a))
            elif env.get(a) is not None:
                vals.append(env[a])
            else:
                missing.append(a)
        known = [v for v in vals if v]
        if m.group(1) == "max":
            if missing:
                return {"value": None, "earliest": max(known).isoformat() if known else None, "missing": missing,
                        "steps": [f"{expr} : {', '.join(missing)} inconnue(s) -> date non déterminée ; "
                                  f"au plus tôt {fmt_date(max(known)) if known else 'inconnue'}"]}
            return {"value": max(vals).isoformat(), "earliest": max(vals).isoformat(), "missing": [],
                    "steps": [f"{expr} = max({', '.join(fmt_date(v) for v in vals)}) = {fmt_date(max(vals))}"]}
        return {"value": None, "earliest": min(known).isoformat() if known else None, "missing": missing or ["choix_de_la_date"],
                "steps": [f"{expr} : règle de choix non explicite -> revue humaine"]}
    if _ISO.fullmatch(expr):
        return {"value": expr, "earliest": expr, "missing": [], "steps": [f"Date explicite : {fmt_date(date.fromisoformat(expr))}"]}
    if env.get(expr) is not None:
        return {"value": env[expr].isoformat(), "earliest": env[expr].isoformat(), "missing": [], "steps": [f"{expr} = {fmt_date(env[expr])}"]}
    return {"value": None, "earliest": None, "missing": [expr], "steps": [f"{expr} inconnue"]}


def shift(d: date, amount: int, unit: str, direction: str) -> date:
    sign = -1 if direction == "before" else 1
    if unit == "months":
        return add_months(d, sign * amount)
    if unit == "years":
        return add_months(d, sign * 12 * amount)
    if unit == "weeks":
        return add_days(d, sign * 7 * amount)
    return add_days(d, sign * amount)


def revision_deadlines(start: dict, rule: dict, first_revision_offset_years: int, max_months: Optional[int],
                       reference: date, horizon: int = 4) -> dict:
    """Échéances de demande de révision à partir d'une date de début (évaluée) et d'une règle relative à l'anniversaire."""
    base = start.get("value") or start.get("earliest")
    exact = start.get("value") is not None
    if base is None:
        return {"deadlines": [], "exact": False, "steps": ["Date de début inconnue : échéances non calculables."],
                "missing": start.get("missing", [])}
    b = date.fromisoformat(base)
    out, steps = [], [f"Base : {'date de début' if exact else 'date de début AU PLUS TÔT'} = {fmt_date(b)}"]
    for n in range(first_revision_offset_years, first_revision_offset_years + horizon):
        ann = add_months(b, 12 * n)
        if max_months is not None and ann > add_months(b, max_months):
            break
        dl = shift(ann, rule["amount"], rule["unit"], rule["direction"])
        out.append({"anniversary": ann.isoformat(), "deadline": dl.isoformat(), "past": dl < reference})
        steps.append(f"Anniversaire n°{n} = {fmt_date(ann)} -> échéance = {fmt_date(ann)} "
                     f"{'−' if rule['direction'] == 'before' else '+'} {rule['amount']} {rule['unit']} = {fmt_date(dl)}")
    if not exact:
        steps.append("Dates AU PLUS TÔT : elles décalent si la date réelle est postérieure (REVIEW_REQUIRED).")
    return {"deadlines": out, "exact": exact, "steps": steps, "missing": start.get("missing", [])}
