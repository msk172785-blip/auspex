"""Comparaison automatique résultat DÛ vs vérité terrain manuelle.

Vérité terrain : data/ground_truth/<contract_id>.json (voir _TEMPLATE.json).
Seuls les fichiers avec "validated": true sont évalués.

Conventions :
- Événements : appariement par type (multi-ensemble). TP = attendu et détecté ; FN = attendu non détecté ;
  FP = détecté non attendu. Un FN sur un type à échéance (DEADLINE_EVENT_TYPES) est un FN CRITIQUE.
- Rappel pondéré : un événement à échéance pèse 3, les autres 1 (les FN à échéance coûtent plus cher).
- Champs : exactitude champ par champ ; un champ attendu absent (null/false) est juste si DÛ ne
  l'a pas affirmé (NOT_FOUND ou False).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .models import DEADLINE_EVENT_TYPES, ContractAnalysis

# Catégories critiques (faux négatif => échec) exprimées dans le vocabulaire historique des vérités terrain :
# échéance de révision, action du titulaire, forclusion, seuil/plafond, nouveau prix dû, avenant, prestation commandée.
CRITICAL_LEGACY_TYPES = DEADLINE_EVENT_TYPES | {"PRICE_REVISION", "PRICE_REVISION_THRESHOLD", "AMENDMENT_PRICE_CHANGE",
                                                "PURCHASE_ORDER_BILLING"}

EVAL_FIELDS = ["revision_exists", "revision_formula", "revision_index", "deadline_rule",
               "supplier_action_required", "forfeiture_exists", "threshold_exists", "revision_source_page"]
BOOL_FIELDS = ["revision_exists", "supplier_action_required", "forfeiture_exists", "threshold_exists"]
DEADLINE_WEIGHT = 3


def _norm_formula(s: Optional[str]) -> str:
    s = (s or "").lower().replace("×", "x").replace("*", "x").replace(",", ".")
    return re.sub(r"\s+", "", s)


def _pred_value(analysis: ContractAnalysis, name: str):
    f = analysis.fields.get(name)
    return f.value if f is not None and f.found else None


def compare_field(name: str, gt: Any, analysis: ContractAnalysis) -> dict:
    pred = _pred_value(analysis, name)
    if name in BOOL_FIELDS:
        ok = bool(gt) == (pred is True)
        return {"field": name, "expected": gt, "predicted": pred, "correct": ok}
    if name == "revision_formula":
        ok = (pred is None) if gt is None else _norm_formula(gt) == _norm_formula(pred)
        return {"field": name, "expected": gt, "predicted": pred, "correct": ok}
    if name == "revision_index":
        if gt is None:
            return {"field": name, "expected": None, "predicted": pred, "correct": pred is None}
        hay = " ".join((pred or {}).get("names", []) + (pred or {}).get("identifiers", [])).lower() if pred else ""
        ok = bool(pred) and all(tok.lower() in hay for tok in gt)
        return {"field": name, "expected": gt, "predicted": pred, "correct": ok}
    if name == "deadline_rule":
        if gt is None:
            return {"field": name, "expected": None, "predicted": pred, "correct": pred is None}
        keys = ("amount", "unit", "direction", "reference")
        ok = bool(pred) and all(pred.get(k) == gt.get(k) for k in keys)
        return {"field": name, "expected": gt, "predicted": {k: pred.get(k) for k in keys} if pred else None, "correct": ok}
    if name == "revision_source_page":
        if gt is None:
            return {"field": name, "expected": None, "predicted": None, "correct": None}  # non applicable
        pages = set()
        for k in ("revision_exists", "revision_formula", "supplier_action_required", "deadline_rule", "forfeiture_exists"):
            f = analysis.fields.get(k)
            if f is not None and f.found:
                pages |= {e.page for e in f.evidence}
        return {"field": name, "expected": gt, "predicted": sorted(pages), "correct": gt in pages}
    raise KeyError(name)


def compare_events(expected: list[dict], analysis) -> dict:
    preds = [{"type": e.financial_event_type, "pages": sorted({x.page for x in e.evidence}), "title": e.title,
              "status": e.status} for e in analysis.events]
    used = [False] * len(preds)
    tp, fn = [], []
    for exp in expected:
        idx = None
        for i, p in enumerate(preds):
            if not used[i] and p["type"] == exp["type"] and exp.get("page") in p["pages"]:
                idx = i
                break
        if idx is None:
            for i, p in enumerate(preds):
                if not used[i] and p["type"] == exp["type"]:
                    idx = i
                    break
        if idx is None:
            fn.append({**exp, "critical": exp.get("critical", exp["type"] in CRITICAL_LEGACY_TYPES)})
        else:
            used[idx] = True
            tp.append({**exp, "predicted_pages": preds[idx]["pages"],
                       "page_ok": exp.get("page") is None or exp.get("page") in preds[idx]["pages"]})
    fp = [p for i, p in enumerate(preds) if not used[i]]
    return {"tp": tp, "fp": fp, "fn": fn}


def evaluate_contract(analysis, gt: dict) -> dict:
    fields = [compare_field(n, gt["fields"].get(n), analysis) for n in EVAL_FIELDS if n in gt.get("fields", {})]
    events = compare_events(gt.get("events", []), analysis)
    return {"contract_id": gt["contract_id"], "SIMULATED_EXAMPLE": gt.get("SIMULATED_EXAMPLE", False),
            "fields": fields, "events": events, "expected_events": len(gt.get("events", [])),
            "detected_events": len(analysis.events)}


def _ratio(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


def aggregate(results: list[dict]) -> dict:
    tp = sum(len(r["events"]["tp"]) for r in results)
    fp = sum(len(r["events"]["fp"]) for r in results)
    fn = sum(len(r["events"]["fn"]) for r in results)
    crit_fn = sum(1 for r in results for x in r["events"]["fn"] if x["critical"])
    w = lambda t: DEADLINE_WEIGHT if t in DEADLINE_EVENT_TYPES else 1  # noqa: E731
    wtp = sum(w(x["type"]) for r in results for x in r["events"]["tp"])
    wfn = sum(w(x["type"]) for r in results for x in r["events"]["fn"])
    page_ok = sum(1 for r in results for x in r["events"]["tp"] if x["page_ok"])
    per_field = {}
    for name in EVAL_FIELDS:
        vals = [f["correct"] for r in results for f in r["fields"] if f["field"] == name and f["correct"] is not None]
        per_field[name] = {"n": len(vals), "correct": sum(vals), "accuracy": _ratio(sum(vals), len(vals))}
    # matrice de confusion des champs booléens (détection de clause)
    btp = bfp = bfn = btn = 0
    for r in results:
        for f in r["fields"]:
            if f["field"] in BOOL_FIELDS:
                e, p = bool(f["expected"]), f["predicted"] is True
                btp += e and p
                bfp += (not e) and p
                bfn += e and not p
                btn += (not e) and not p
    return {
        "contracts": len(results),
        "simulated_contracts": sum(1 for r in results if r["SIMULATED_EXAMPLE"]),
        "expected_events": sum(r["expected_events"] for r in results),
        "detected_events": sum(r["detected_events"] for r in results),
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "critical_false_negatives": crit_fn,
        "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
        "weighted_recall": _ratio(wtp, wtp + wfn),
        "event_page_accuracy": _ratio(page_ok, tp),
        "fields": per_field,
        "clause_detection": {"tp": btp, "fp": bfp, "fn": bfn, "tn": btn,
                             "precision": _ratio(btp, btp + bfp), "recall": _ratio(btp, btp + bfn)},
    }


def error_list(results: list[dict]) -> list[str]:
    out = []
    for r in results:
        cid = r["contract_id"]
        for x in r["events"]["fn"]:
            out.append(f"[{'FN CRITIQUE' if x['critical'] else 'FN'}] {cid} : événement attendu non détecté {x['type']} (page {x.get('page')})")
        for x in r["events"]["fp"]:
            out.append(f"[FP] {cid} : événement détecté non attendu {x['type']} (pages {x['pages']}) — {x['title']}")
        for x in r["events"]["tp"]:
            if not x["page_ok"]:
                out.append(f"[PAGE] {cid} : {x['type']} attendu page {x.get('page')}, preuves pages {x['predicted_pages']}")
        for f in r["fields"]:
            if f["correct"] is False:
                out.append(f"[CHAMP] {cid} : {f['field']} attendu={f['expected']!r} obtenu={f['predicted']!r}")
    return out
