"""Reason -> monitorable assertions (V0.4).

Turns a holding reason into 2-3 watchable INVALIDATION conditions. Each is tagged:
- monitor "auto" + rewindable True  : daily series (price, P/E) -> 12-month rewind works.
- monitor "auto" + rewindable False : snapshot fundamental -> monitored forward, not rewound.
- monitor "manual"                  : qualitative -> never claimed as monitored.

Anthropic (Claude) chooses metric/operator/threshold if a key is present. When the
Claude call fails for any reason, we fall back to a deterministic heuristic AND report
why via engine_note, so the fallback is observable, not silent.
"""
from __future__ import annotations
from typing import Optional
import json

from app.models import Fundamentals
from app.config import settings
from app.services import constitution as C

METRICS = {
    "price":            {"label": "Price", "unit": "price", "rewindable": True},
    "pe":               {"label": "P/E (trailing)", "unit": "x", "rewindable": True},
    "pe_percentile":    {"label": "P/E vs its 1-year range", "unit": "percentile", "rewindable": True},
    "revenue_growth":   {"label": "Revenue growth (YoY)", "unit": "pct", "rewindable": False},
    "profit_margin":    {"label": "Net margin", "unit": "pct", "rewindable": False},
    "gross_margin":     {"label": "Gross margin", "unit": "pct", "rewindable": False},
    "operating_margin": {"label": "Operating margin", "unit": "pct", "rewindable": False},
    "roe":              {"label": "Return on equity", "unit": "pct", "rewindable": False},
    "target_mean":      {"label": "Analyst mean target", "unit": "price", "rewindable": False},
    "days_to_earnings": {"label": "Days to next earnings", "unit": "days", "rewindable": False},
}
MANUAL = "manual"


def _snapshot(f: Fundamentals) -> dict:
    pct = lambda v: None if v is None else round(v * 100, 1)
    return {
        "price": f.price, "pe": f.pe_trailing, "pe_percentile": f.pe_history_percentile,
        "revenue_growth": pct(f.revenue_growth), "profit_margin": pct(f.profit_margin),
        "gross_margin": pct(f.gross_margin), "operating_margin": pct(f.operating_margin),
        "roe": pct(f.roe), "target_mean": f.target_mean, "days_to_earnings": f.days_to_earnings,
        "week52_high": f.week52_high, "week52_low": f.week52_low,
    }


def _fmt(metric, value):
    if value is None:
        return "n/a"
    u = METRICS.get(metric, {}).get("unit")
    if u == "pct": return f"{value:g}%"
    if u == "x": return f"{value:g}x"
    if u == "percentile": return f"the {int(value)}th percentile"
    if u == "days": return f"{int(value)} days"
    return f"{value:g}"


def _assertion(metric, operator, threshold, basis=""):
    if metric == MANUAL:
        label, text, rewindable, monitor = "Manual check", \
            "A condition that cannot be measured from market data", False, "manual"
    else:
        m = METRICS[metric]
        label = m["label"]
        verb = "rises above" if operator == "above" else "falls below"
        text = f"{label} {verb} {_fmt(metric, threshold)}"
        rewindable, monitor = bool(m["rewindable"]), "auto"
    basis = (basis or "").strip()
    if basis and not C.is_conformant(basis):
        basis = ""
    return {"metric": metric, "operator": operator, "threshold": threshold,
            "unit": METRICS.get(metric, {}).get("unit", "manual"), "label": label,
            "text": text, "monitor": monitor, "rewindable": rewindable, "basis": basis}


def _select(cands, snap):
    seen, ded = set(), []
    for a in cands:
        k = (a["metric"], a["operator"])
        if k not in seen:
            seen.add(k); ded.append(a)
    rew = [a for a in ded if a["rewindable"]]
    man = [a for a in ded if a["monitor"] == "manual"]
    snp = [a for a in ded if a["monitor"] == "auto" and not a["rewindable"]]
    if not rew:
        px = snap.get("price")
        if px:
            rew = [_assertion("price", "below", round(px * 0.8, 2),
                              "A protective price level for this position.")]
    out = []
    if rew: out.append(rew[0])
    if man: out.append(man[0])
    for a in snp + rew[1:] + man[1:]:
        if len(out) >= 3:
            break
        if a not in out:
            out.append(a)
    if not out:
        out = [_assertion("price", "below", round((snap.get("price") or 100) * 0.8, 2))]
    return out[:3]


def _heuristic(reason, exit_condition, snap):
    r = (reason or "").lower() + " " + (exit_condition or "").lower()
    has = lambda *w: any(x in r for x in w)
    c = []
    if has("cheap", "undervalued", "value", "discount", "bargain", "low p/e", "low pe", "attractive valuation"):
        c.append(_assertion("pe_percentile", "above", 70, "The reason rests on a low valuation."))
    if has("grow", "growth", "revenue", "expanding", "compounding"):
        cur = snap.get("revenue_growth"); thr = 10 if cur is None else max(0, round(cur * 0.5))
        c.append(_assertion("revenue_growth", "below", thr, "The reason rests on continued growth."))
    if has("margin", "profitab", "efficient", "pricing power"):
        cur = snap.get("profit_margin"); thr = 15 if cur is None else max(0, round(cur * 0.8))
        c.append(_assertion("profit_margin", "below", thr, "The reason rests on strong margins."))
    if has("upside", "target", "analyst"):
        tm = snap.get("target_mean")
        if tm:
            c.append(_assertion("price", "above", round(tm, 2), "The reason rests on remaining upside to target."))
    if has("moat", "brand", "management", "ceo", "leader", "dominant", "ecosystem",
           "network effect", "product", "roadmap", "market share", "regulat", "competiti", "quality"):
        c.append(_assertion(MANUAL, "n/a", None))
    return _select(c, snap)


_SYSTEM = (
    "You convert an investor's reason for holding a stock into 2-3 monitorable "
    "INVALIDATION conditions whose breach would mean the reason no longer holds. You "
    "never give opinions, never recommend buying or selling, never judge. Output STRICT JSON only."
)


def _anthropic(reason, exit_condition, snap):
    """Returns (assertions_or_None, note). note is None on success."""
    from app.services import llm
    prompt = (
        "Allowed metric ids: " + ", ".join(METRICS.keys()) + ", or \"manual\" for anything "
        "qualitative (moat, management, product, regulation, market share).\n"
        "Current snapshot for sensible thresholds: " + json.dumps(snap) + "\n"
        "Reason for holding: " + json.dumps(reason) + "\n"
        "Optional exit condition: " + json.dumps(exit_condition or "") + "\n\n"
        "Return strict JSON {\"assertions\":[{\"metric\":\"<id|manual>\",\"operator\":\"above|below\","
        "\"threshold\":<number|null>,\"basis\":\"<short neutral phrase>\"}]}. Give 2-3. Prefer at least "
        "one price/pe/pe_percentile condition. percentile 0-100, pct like 15 for 15%, price absolute."
    )
    raw, err = llm.anthropic_json(_SYSTEM, prompt)
    if err:
        return None, err
    if not raw:
        return None, "empty_response"
    try:
        js = raw[raw.find("{"):raw.rfind("}") + 1]
        data = json.loads(js)
    except Exception as e:
        return None, "parse_error: %s" % (str(e)[:120])
    c = []
    for it in (data.get("assertions") or [])[:4]:
        metric = (it.get("metric") or "").strip()
        if metric not in METRICS and metric != MANUAL:
            metric = MANUAL
        op = "below" if str(it.get("operator", "")).lower().startswith("b") else "above"
        thr = it.get("threshold")
        try:
            thr = None if thr is None else float(thr)
        except Exception:
            thr = None
        if metric != MANUAL and thr is None:
            continue
        c.append(_assertion(metric, op, thr, it.get("basis", "")))
    if not c:
        return None, "no_usable_assertions"
    return _select(c, snap), None


def decompose_reason(reason, exit_condition, f: Fundamentals) -> dict:
    snap = _snapshot(f)
    engine, note, assertions = "heuristic", None, None
    if settings.ANTHROPIC_API_KEY:
        assertions, note = _anthropic(reason, exit_condition, snap)
        if assertions:
            engine = "anthropic"
    else:
        note = "no_key"
    if not assertions:
        assertions = _heuristic(reason, exit_condition, snap)
    for i, a in enumerate(assertions):
        a["id"] = "a" + str(i + 1)
    return {"assertions": assertions, "engine": engine, "engine_note": note,
            "model": settings.ANTHROPIC_MODEL, "snapshot": snap}
