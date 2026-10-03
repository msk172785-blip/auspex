"""Moteur hybride DÛ v1 — orchestration.

PDF/texte -> segmentation -> candidats larges -> interprétation (cadres locaux [+ LLM optionnel])
-> vérification stricte -> normalisation/fusion -> calculs déterministes -> cohérence
-> checklist critique avec revue humaine obligatoire.
La baseline regex (du_engine.extractor) tourne en parallèle comme signal auxiliaire.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date
from types import SimpleNamespace
from typing import Any, Optional

from .. import calculations as calc
from ..extractor import extract_amendment_price_changes, extract_fields
from ..models import DocumentText
from . import coherence, dates
from . import lexicon as L
from .candidates import generate
from .document import StructuredDocument, build, squash
from .frames import FrameInterpreter
from .llm import LLMInterpreter
from .schema import (AUTO_EXTRACTED, CRITICAL_TYPES, REJECTED_UNSUPPORTED, REVIEW_REQUIRED, Amount, Clause, Evidence)
from .verify import Verifier

ENGINE_VERSION = "v1.0"

CRITICAL_CATEGORIES = {
    "echeance_revision": ["PRICE_REVISION_DEADLINE"],
    "action_obligatoire_titulaire": ["SUPPLIER_ACTION_REQUIRED", "PRICE_REVISION_DEADLINE", "BILLING_CONDITION"],
    "forclusion_perte_de_droit": ["CONSEQUENCE_IF_NO_ACTION"],
    "seuil_ou_plafond_revision": ["PRICE_REVISION_THRESHOLD"],
    "nouveau_prix_du": ["PRICE_REVISION"],
    "avenant_modifiant_le_prix": ["AMENDMENT_PRICE_CHANGE"],
    "prestation_commandee_facturable": ["PURCHASE_ORDER_BILLING", "BILLING_CONDITION"],
}

LEGACY = {"PRICE_REVISION": "PRICE_REVISION", "PRICE_REVISION_DEADLINE": "PRICE_REVISION_DEADLINE",
          "PRICE_REVISION_THRESHOLD": "PRICE_REVISION_THRESHOLD", "AMENDMENT_PRICE_CHANGE": "AMENDMENT_PRICE_CHANGE",
          "PURCHASE_ORDER_BILLING": "PURCHASE_ORDER_BILLING", "VARIABLE_SERVICE_BILLING": "VARIABLE_SERVICE_BILLING",
          "RETENTION_RELEASE": "RETENTION_RELEASE", "FINAL_BALANCE": "FINAL_BALANCE",
          "LATE_PAYMENT_INTEREST": "OTHER_FINANCIAL_RIGHT", "ADVANCE_PAYMENT": "OTHER_FINANCIAL_RIGHT",
          "REEXAMINATION_RIGHT": "OTHER_FINANCIAL_RIGHT"}


def _quote_key(c: Clause) -> str:
    return "|".join(sorted(f"{e.start}" for e in c.evidence if e.start is not None)) or c.source_quote[:80]


def _merge(clauses: list[Clause]) -> list[Clause]:
    """Fusionne les doublons (même type, mêmes preuves). Désaccord FRAMES/LLM sur les rôles => REVIEW."""
    out: dict[tuple, Clause] = {}
    rejected = [c for c in clauses if c.status == REJECTED_UNSUPPORTED]
    for c in clauses:
        if c.status == REJECTED_UNSUPPORTED:
            continue
        k = (c.event_type, _quote_key(c))
        if k not in out:
            out[k] = c
            continue
        a = out[k]
        if a.interpreter != c.interpreter:
            ra = sorted((p.value, p.role) for p in a.percentages)
            rc = sorted((p.value, p.role) for p in c.percentages)
            if ra != rc or sorted((x.value, x.role) for x in a.amounts) != sorted((x.value, x.role) for x in c.amounts):
                a.review_reasons.append(f"Désaccord {a.interpreter}/{c.interpreter} sur les rôles des nombres.")
                if a.status == AUTO_EXTRACTED:
                    a.status = REVIEW_REQUIRED
            else:
                a.checks.append(f"OK: confirmé par {c.interpreter}")
            a.interpreter = f"{a.interpreter}+{c.interpreter}"
    return list(out.values()) + rejected


SECTION_MERGE_TYPES = {"LATE_PAYMENT_INTEREST", "VARIABLE_SERVICE_BILLING", "PRICE_REVISION_THRESHOLD", "ADVANCE_PAYMENT",
                       "REEXAMINATION_RIGHT", "PENALTY_EXPOSURE", "PAYMENT_TERM"}


def _merge_by_section(clauses: list[Clause]) -> list[Clause]:
    """Une clause par (type, section) pour les types descriptifs ; les sous-types (plafond annuel/cumulé,
    sauvegarde) restent distincts DANS la clause (pourcentages et attributs), jamais confondus."""
    keep, groups = [], {}
    for c in clauses:
        if c.event_type in SECTION_MERGE_TYPES and c.status != REJECTED_UNSUPPORTED and c.section_id:
            groups.setdefault((c.event_type, c.section_id), []).append(c)
        else:
            keep.append(c)
    for (_, _), cs in groups.items():
        head = cs[0]
        for c in cs[1:]:
            seen = {e.start for e in head.evidence}
            head.evidence += [e for e in c.evidence if e.start not in seen]
            have = {(p.value, p.role, p.subrole) for p in head.percentages}
            head.percentages += [p for p in c.percentages if (p.value, p.role, p.subrole) not in have]
            have_a = {(a.value, a.role) for a in head.amounts}
            head.amounts += [a for a in c.amounts if (a.value, a.role) not in have_a]
            kinds = set(filter(None, str(head.attributes.get("kind", "")).split("+"))) | set(filter(None, str(c.attributes.get("kind", "")).split("+")))
            if kinds:
                head.attributes["kind"] = "+".join(sorted(kinds))
            head.review_reasons += [r for r in c.review_reasons if r not in head.review_reasons]
            head.checks += [x for x in c.checks if x not in head.checks]
            if c.status == REVIEW_REQUIRED:
                head.status = REVIEW_REQUIRED
        keep.append(head)
    # une action fournisseur déjà portée par une échéance (même phrase) n'est pas dupliquée
    dl_quotes = {e.start for c in keep if c.event_type == "PRICE_REVISION_DEADLINE" for e in c.evidence}
    keep = [c for c in keep if not (c.event_type == "SUPPLIER_ACTION_REQUIRED" and {e.start for e in c.evidence} <= dl_quotes)]
    return keep


def _merge_price_revision(clauses: list[Clause]) -> list[Clause]:
    """Un seul événement PRICE_REVISION par document : union des preuves et des attributs."""
    pr = [c for c in clauses if c.event_type == "PRICE_REVISION" and c.status != REJECTED_UNSUPPORTED]
    if len(pr) <= 1:
        return clauses
    pr.sort(key=lambda c: (not c.attributes.get("in_price_section"), c.evidence[0].start or 0))
    head = pr[0]
    for c in pr[1:]:
        seen = {e.start for e in head.evidence}
        head.evidence += [e for e in c.evidence if e.start not in seen]
        for k, v in c.attributes.items():
            head.attributes.setdefault(k, v)
        if c.trigger and not head.trigger:
            head.trigger = c.trigger
        head.review_reasons += [r for r in c.review_reasons if r not in head.review_reasons]
        head.confidence = max(head.confidence, c.confidence)
    if any(c.status == REVIEW_REQUIRED for c in pr):
        head.status = REVIEW_REQUIRED
    return [c for c in clauses if c not in pr[1:]]


def _amendments(doc: DocumentText, sd: StructuredDocument, invoices: list[dict]) -> list[Clause]:
    out = []
    v = Verifier(sd)
    for ch in extract_amendment_price_changes(doc):
        c = Clause(event_type="AMENDMENT_PRICE_CHANGE", interpreter="FRAMES", confidence=0.85,
                   evidence=[Evidence(document=sd.name, page=ch["evidence"].page, page_end=None, article=None, quote=ch["evidence"].quote)],
                   amounts=[Amount(ch["old_unit_price"], "EUR", "OLD_UNIT_PRICE"), Amount(ch["new_unit_price"], "EUR", "NEW_UNIT_PRICE")],
                   attributes={k: ch[k] for k in ("label", "item_code", "effective_date", "tax")}, actor="SUPPLIER", actor_basis="INFERRED_FROM_SECTION")
        if ch["effective_date"] is None:
            c.missing_information.append("date d'effet de l'avenant")
        v.verify(c)
        if invoices and c.status != REJECTED_UNSUPPORTED and ch["item_code"] and ch["effective_date"]:
            eff = date.fromisoformat(ch["effective_date"])
            qty, lines = calc.D(0), []
            for inv in invoices:
                idate = date.fromisoformat(inv["date"])
                for ln in inv.get("lines", []):
                    if ln.get("item_code") == ch["item_code"] and idate >= eff and calc.D(ln["unit_price"]) == calc.D(ch["old_unit_price"]):
                        qty += calc.D(ln["quantity"])
                        lines.append(f"{inv['invoice_id']} ({inv['date']}) : {ln['quantity']} × {ln['unit_price']} €")
            if qty:
                r = calc.amendment_underbilling(ch["old_unit_price"], ch["new_unit_price"], qty)
                c.attributes["calculation"] = {"underbilled_amount": float(r.value), "lines": lines, "steps": r.steps}
                c.attributes["potential_amount"] = float(r.value)
        elif not invoices:
            c.missing_information.append("factures (pour vérifier l'application du nouveau prix)")
            if c.status == AUTO_EXTRACTED:
                c.status = REVIEW_REQUIRED
        out.append(c)
    return out


def _uncovered(sd: StructuredDocument, cands, clauses: list[Clause]) -> list[dict]:
    spans = [(e.start, e.end) for c in clauses if c.status != REJECTED_UNSUPPORTED for e in c.evidence if e.start is not None]
    out = []
    for cand in cands:
        if not cand.strong:
            continue
        p = sd.paragraphs[cand.paragraph]
        if any(a < p.end and z > p.start for a, z in spans):
            continue
        sec = sd.section(cand.section)
        out.append({"page": cand.page, "article": sec.number, "patterns": cand.strong, "text": cand.text[:300],
                    "status": REVIEW_REQUIRED, "reason": "Zone économique forte non couverte par une interprétation vérifiée."})
    return out


def _baseline_signals(docs: list[DocumentText], events: list[dict]) -> list[dict]:
    fields, _ = extract_fields(docs)
    have = {e["event_type"] for e in events}
    checks = [("revision_exists", True, {"PRICE_REVISION"}), ("deadline_rule", None, {"PRICE_REVISION_DEADLINE"}),
              ("supplier_action_required", True, {"SUPPLIER_ACTION_REQUIRED", "PRICE_REVISION_DEADLINE"}),
              ("forfeiture_exists", True, {"CONSEQUENCE_IF_NO_ACTION"}), ("cap_exists", True, {"PRICE_REVISION_THRESHOLD"}),
              ("threshold_exists", True, {"PRICE_REVISION_THRESHOLD"}), ("purchase_orders_exist", True, {"PURCHASE_ORDER_BILLING"})]
    out = []
    for name, expected, types in checks:
        f = fields.get(name)
        if f is None or not f.found or (expected is not None and f.value != expected):
            continue
        ev = f.first_evidence
        out.append({"baseline_field": name, "baseline_value": f.value, "page": ev.page if ev else None,
                    "explained_by_v1": bool(have & types),
                    "status": "OK" if have & types else REVIEW_REQUIRED})
    return out


def analyze_v1(docs: list[DocumentText], user_inputs: Optional[dict] = None, recon: Optional[dict] = None,
               reference_date: Optional[date] = None, use_llm: bool = False, llm_client: Any = None,
               simulated: bool = False, contract_key: str = "contract") -> dict:
    user = {k: v for k, v in (user_inputs or {}).items() if v not in (None, "")}
    recon = recon or {}
    ref = reference_date or date.today()
    warnings: list[str] = []
    all_clauses: list[Clause] = []
    terms: list[Clause] = []
    candidates_log, uncovered, anomalies, llm_log = [], [], [], []
    structures = {}
    for d in docs:
        warnings += [f"{d.name} : {w}" for w in d.warnings]
        if not d.has_text_layer:
            continue
        sd = build(d)
        structures[d.name] = sd
        anomalies += [f"{d.name} : {a}" for a in sd.anomalies]
        if not simulated and any("EXEMPLE SIMULÉ" in t.upper() for t in list(sd.pages_raw.values())[:2]):
            simulated = True
            warnings.append("Document marqué « EXEMPLE SIMULÉ » : analyse traitée comme une simulation.")
        if d.doc_type == "AMENDMENT":
            all_clauses += _amendments(d, sd, recon.get("invoices", []))
            continue
        cands = generate(sd)
        candidates_log += [{"document": d.name, "page": c.page, "article": sd.section(c.section).number,
                            "concepts": sorted(c.concepts), "strong": c.strong} for c in cands]
        fi = FrameInterpreter(sd)
        clauses = fi.interpret()
        doc_terms = fi.contract_terms()
        if use_llm:
            li = LLMInterpreter(sd, client=llm_client)
            clauses += li.interpret(cands)
            llm_log += li.log
        v = Verifier(sd)
        for c in clauses + doc_terms:
            v.verify(c)
        clauses = _merge(clauses)
        uncovered += [{"document": d.name, **u} for u in _uncovered(sd, cands, clauses + doc_terms)]
        all_clauses += clauses
        terms += doc_terms
    if not structures:
        warnings.append("Aucun document exploitable : aucune clause ne peut être extraite.")

    all_clauses = _merge_by_section(_merge_price_revision(all_clauses))
    coherence_report = coherence.run(all_clauses + terms)

    # ---------------- faits du contrat : début, durée, valeur annuelle
    env = {"notification_date": date.fromisoformat(user["notification_date"]) if user.get("notification_date") else None}
    start_c = next((c for c in terms if c.event_type == "CONTRACT_START" and c.status != REJECTED_UNSUPPORTED), None)
    dur_c = next((c for c in terms if c.event_type == "CONTRACT_DURATION" and c.status != REJECTED_UNSUPPORTED), None)
    if user.get("contract_start_date"):
        start = {"value": user["contract_start_date"], "earliest": user["contract_start_date"], "missing": [],
                 "steps": ["Date de début saisie par l'utilisateur (non vérifiée dans le document)."], "kind": "USER_INPUT",
                 "document_expression": start_c.date_expression if start_c else None}
    elif start_c:
        start = {**dates.evaluate(start_c.date_expression, env), "kind": "DOCUMENT", "expression": start_c.date_expression}
    else:
        start = {"value": None, "earliest": None, "missing": ["contract_start_date"], "steps": ["Aucune date de début trouvée."], "kind": "MISSING"}
    max_months = dur_c.attributes.get("max_months") if dur_c else None
    if dur_c and max_months and dur_c.attributes.get("stated_last_date") and start.get("earliest"):
        end_calc = calc.add_days(calc.add_months(date.fromisoformat(start["earliest"]), max_months), -1).isoformat()
        dur_c.attributes["computed_last_date_from_earliest_start"] = end_calc
        if end_calc == dur_c.attributes["stated_last_date"]:
            dur_c.checks.append(f"OK: début au plus tôt + {max_months} mois − 1 jour = {end_calc} = dernière date énoncée")
        else:
            dur_c.review_reasons.append(f"Fin calculée {end_calc} ≠ dernière date énoncée {dur_c.attributes['stated_last_date']}.")
            dur_c.status = REVIEW_REQUIRED
    annual_value = None
    for c in terms:
        if c.event_type == "CONTRACT_VALUE" and c.status != REJECTED_UNSUPPORTED:
            annual_value = {"value": c.amounts[0].value, "kind": "DOCUMENT", "page": c.source_page, "status": c.status}
    for c in all_clauses:
        for a in c.amounts:
            if a.role == "ANNUAL_CONTRACT_VALUE" and c.status != REJECTED_UNSUPPORTED:
                annual_value = {"value": a.value, "kind": "DOCUMENT", "page": c.source_page}
    if user.get("annual_amount") is not None:
        annual_value = {"value": float(user["annual_amount"]), "kind": "USER_INPUT"}

    # ---------------- calculs déterministes rattachés aux clauses
    caps = [p for c in all_clauses if c.status != REJECTED_UNSUPPORTED for p in c.percentages if p.role == "CAP"]
    cap_annual = next((p.value for p in caps if p.subrole == "CAP_ANNUAL"), None)
    trig = next((p.value for c in all_clauses if c.status != REJECTED_UNSUPPORTED for p in c.percentages if p.subrole == "TRIGGER_THRESHOLD"), None)
    revision_calc = None
    pr = next((c for c in all_clauses if c.event_type == "PRICE_REVISION" and c.status != REJECTED_UNSUPPORTED), None)
    if pr:
        formula = pr.attributes.get("formula")
        coef = calc.revision_coefficient(formula, user.get("index_base"), user.get("index_new"), user.get("revision_coefficient"))
        missing = list(coef.missing_information)
        if annual_value is None:
            missing.append("montant annuel du marché (le maximum des bons de commande n'est pas utilisé)")
        if coef.value is not None and annual_value is not None:
            r = calc.revision_delta(annual_value["value"], coef.value, trig, cap_annual)
            revision_calc = {**r.to_dict()["value"], "steps": coef.steps + r.steps}
        pr.attributes["calculation"] = revision_calc
        pr.missing_information += [m for m in missing if m not in pr.missing_information]
        if pr.missing_information and pr.status == AUTO_EXTRACTED:
            pr.status = REVIEW_REQUIRED
    for c in all_clauses:
        if c.status == REJECTED_UNSUPPORTED or not c.deadline_rule:
            continue
        if c.event_type in ("PRICE_REVISION_DEADLINE", "CONSEQUENCE_IF_NO_ACTION", "SUPPLIER_ACTION_REQUIRED") and \
                c.deadline_rule.get("anchor") == "ANNIVERSARY" and c.deadline_rule.get("amount"):
            first = 1
            res = dates.revision_deadlines(start, c.deadline_rule, first, max_months, ref)
            c.attributes["deadlines"] = res
            nxt = next((x for x in res["deadlines"] if not x["past"]), None)
            c.attributes["next_deadline"] = nxt["deadline"] if nxt else None
            c.attributes["next_deadline_exact"] = res["exact"]
            if not res["exact"]:
                c.missing_information += [m for m in (res["missing"] or ["date de début exacte"]) if m not in c.missing_information]
                if c.status == AUTO_EXTRACTED:
                    c.status = REVIEW_REQUIRED
            if revision_calc:
                c.attributes["potential_amount"] = float(revision_calc["potential_delta"])

    # ---------------- rapprochements (P2) : bons de commande, retenue
    pos, invoices = recon.get("purchase_orders", []), recon.get("invoices", [])
    po_clause = next((c for c in all_clauses if c.event_type == "PURCHASE_ORDER_BILLING" and c.status != REJECTED_UNSUPPORTED), None)
    if pos:
        billed = {}
        for inv in invoices:
            for ln in inv.get("lines", []):
                if ln.get("po_ref"):
                    billed[ln["po_ref"]] = billed.get(ln["po_ref"], calc.D(0)) + calc.D(ln.get("amount") or calc.D(ln["unit_price"]) * calc.D(ln["quantity"]))
        gaps = []
        for p in pos:
            if p.get("status") == "REALISEE" and billed.get(p["po_id"], calc.D(0)) < calc.D(p["amount"]):
                r = calc.unbilled_amount(p["amount"], billed.get(p["po_id"], calc.D(0)))
                gaps.append({"po_id": p["po_id"], "label": p.get("label"), "unbilled_amount": float(r.value), "steps": r.steps})
        if po_clause:
            po_clause.attributes["reconciliation"] = gaps
            if gaps:
                po_clause.attributes["potential_amount"] = sum(g["unbilled_amount"] for g in gaps)
    elif po_clause:
        po_clause.missing_information.append("liste des bons de commande et factures (rapprochement)")
    ret = next((c for c in all_clauses if c.event_type == "RETENTION_RELEASE" and c.status != REJECTED_UNSUPPORTED), None)
    if ret:
        ledger = recon.get("retention")
        if not ledger:
            ret.missing_information.append("montants retenus et règlements")
        else:
            txt = " ".join(e.quote for e in ret.evidence)
            sd_any = next(iter(structures.values()))
            sec_txt = squash(sd_any.section_text(ret.section_id)) if ret.section_id else txt
            g = re.search(r"d[ée]lai\s+de\s+garantie[^.;]{0,40}?(" + L.NUM_WORD + r")\s*(mois|ans?)", sec_txt, re.I)
            rel = re.search(r"(" + L.NUM_WORD + r")\s*mois\s+apr[eè]s\s+l'expiration\s+du\s+d[ée]lai\s+de\s+garantie", sec_txt, re.I)
            retained = sum((calc.D(x["amount"]) for x in ledger.get("retained", [])), calc.D(0))
            released = sum((calc.D(x["amount"]) for x in ledger.get("payments", []) if x.get("type") == "RETENTION_RELEASE"), calc.D(0))
            steps = [f"Montant retenu = {calc.fmt_eur(retained)}", f"Montant libéré = {calc.fmt_eur(released)}"]
            due = None
            if g and rel and ledger.get("reception_date"):
                gm = L.to_int(g.group(1)) * (12 if L.unit_norm(g.group(2)) == "years" else 1)
                end_g = calc.add_months(date.fromisoformat(ledger["reception_date"]), gm)
                due = calc.add_months(end_g, L.to_int(rel.group(1)))
                steps += [f"Fin de garantie = réception {calc.fmt_date(date.fromisoformat(ledger['reception_date']))} + {gm} mois = {calc.fmt_date(end_g)}",
                          f"Libération exigible = {calc.fmt_date(end_g)} + {L.to_int(rel.group(1))} mois = {calc.fmt_date(due)}"]
            else:
                ret.missing_information.append("délai de garantie / règle de libération / date de réception")
            out_amt = calc.money(retained - released)
            ret.attributes["calculation"] = {"retained": float(retained), "released": float(released), "outstanding": float(out_amt),
                                             "release_due_date": due.isoformat() if due else None,
                                             "condition_met": bool(due and due <= ref), "steps": steps}
            if due and due <= ref and out_amt > 0:
                ret.attributes["potential_amount"] = float(out_amt)

    # ---------------- événements, criticité, revue humaine
    events = []
    for i, c in enumerate(sorted(all_clauses, key=lambda x: (x.source_page or 0, x.event_type))):
        c.critical = c.event_type in CRITICAL_TYPES
        if c.event_type == "CONSEQUENCE_IF_NO_ACTION" and (c.consequence_if_no_action or {}).get("polarity_for_supplier") == "FAVORABLE":
            c.attributes["note_polarity"] = "Conséquence FAVORABLE au titulaire (inaction de l'acheteur)."
        c.human_review_required = c.critical
        d = c.to_dict()
        d["id"] = f"E{i + 1}"
        d["legacy_type"] = LEGACY.get(c.event_type)
        if c.event_type == "CONSEQUENCE_IF_NO_ACTION" and c.attributes.get("related_to") == "PRICE_REVISION" \
                and (c.consequence_if_no_action or {}).get("polarity_for_supplier") == "UNFAVORABLE":
            d["legacy_type"] = "PRICE_REVISION_FORFEITURE"
        d["SIMULATED_EXAMPLE"] = simulated
        events.append(d)

    rejected = [e for e in events if e["status"] == REJECTED_UNSUPPORTED]
    live = [e for e in events if e["status"] != REJECTED_UNSUPPORTED]
    checklist = {}
    for cat, types in CRITICAL_CATEGORIES.items():
        hits = [e["id"] for e in live if e["event_type"] in types]
        checklist[cat] = {"outcome": "FOUND" if hits else "NOT_FOUND", "events": hits,
                          "human_review_required": True,
                          "examined_candidate_zones": sum(1 for c in candidates_log),
                          "uncovered_strong_zones": [u for u in uncovered if (cat.startswith("forclusion") and "CONSEQUENCE" in u["patterns"])
                                                     or (cat in ("nouveau_prix_du", "echeance_revision") and "PRICE_CHANGE" in u["patterns"])]}
        if not hits and checklist[cat]["uncovered_strong_zones"]:
            checklist[cat]["outcome"] = REVIEW_REQUIRED

    contract = {
        "start_date": start,
        "start_evidence": [asdict(e) for e in start_c.evidence] if start_c else [],
        "duration": dur_c.attributes if dur_c else None,
        "duration_evidence": [asdict(e) for e in dur_c.evidence] if dur_c else [],
        "duration_status": dur_c.status if dur_c else "NOT_FOUND",
        "duration_review": dur_c.review_reasons if dur_c else [],
        "annual_contract_value": annual_value,
        "payment_terms": [e["deadline_rule"] for e in live if e["event_type"] == "PAYMENT_TERM"],
    }
    return {
        "engine": ENGINE_VERSION, "contract_key": contract_key, "documents": [d.name for d in docs],
        "reference_date": ref.isoformat(), "user_inputs": user, "SIMULATED_EXAMPLE": simulated,
        "interpreters": ["FRAMES"] + (["LLM"] if use_llm else []), "llm_log": llm_log,
        "warnings": warnings, "document_anomalies": anomalies, "contract": contract,
        "events": live, "rejected_unsupported": rejected, "uncovered_candidates": uncovered,
        "critical_checklist": checklist, "coherence_checks": coherence_report,
        "baseline_signals": _baseline_signals(docs, live),
        "segmentation": {n: {"sections": [{"number": s.number, "title": s.title, "level": s.level, "page_start": s.page_start,
                                           "page_end": s.page_end} for s in sd.sections],
                             "paragraphs": len(sd.paragraphs), "sentences": len(sd.sentences),
                             "boilerplate_removed": sd.boilerplate_lines} for n, sd in structures.items()},
        "candidates": candidates_log,
    }


# ---------------- adaptateur vers le schéma d'évaluation historique
def legacy_view(result: dict) -> SimpleNamespace:
    """Expose le résultat v1 sous la forme attendue par evaluation.py (champs + événements historiques)."""
    ev = result["events"]

    def fld(value, events_):
        evs = [SimpleNamespace(page=x["page"]) for e in events_ for x in e["evidence"]]
        return SimpleNamespace(found=value is not None, value=value, evidence=evs)

    pr = [e for e in ev if e["event_type"] == "PRICE_REVISION"]
    dl = [e for e in ev if e["event_type"] == "PRICE_REVISION_DEADLINE"]
    act = [e for e in ev if e["event_type"] in ("SUPPLIER_ACTION_REQUIRED", "PRICE_REVISION_DEADLINE") and e["actor"] == "SUPPLIER"]
    ff = [e for e in ev if e["event_type"] == "CONSEQUENCE_IF_NO_ACTION" and e["attributes"].get("related_to") == "PRICE_REVISION"]
    thr = [e for e in ev for p in e["percentages"] if p["subrole"] == "TRIGGER_THRESHOLD"]
    idx = None
    if pr:
        a = pr[0]["attributes"]
        names = [a["index_name"]] if a.get("index_name") else []
        if a.get("index_identifiers") or names:
            idx = {"names": names, "identifiers": a.get("index_identifiers", [])}
    rule = None
    if dl:
        r = dl[0]["deadline_rule"]
        rule = {"amount": r.get("amount"), "unit": r.get("unit"), "direction": r.get("direction"),
                "reference": "anniversary" if r.get("anchor") == "ANNIVERSARY" else (r.get("anchor") or "").lower()}
    fields = {
        "revision_exists": fld(True if pr else None, pr),
        "revision_formula": fld(pr[0]["attributes"].get("formula") if pr else None, pr),
        "revision_index": fld(idx, pr),
        "deadline_rule": fld(rule, dl),
        "supplier_action_required": fld(True if act else None, act),
        "forfeiture_exists": fld(True if ff else None, ff),
        "threshold_exists": fld(True if thr else None, []),
    }
    events = []
    for e in ev:
        if not e["legacy_type"]:
            continue
        if e["event_type"] == "PURCHASE_ORDER_BILLING" and e["attributes"].get("reconciliation"):
            for g in e["attributes"]["reconciliation"]:
                events.append(SimpleNamespace(financial_event_type="PURCHASE_ORDER_BILLING", title=f"BC {g['po_id']} non facturé",
                                              status=e["status"], evidence=[SimpleNamespace(page=x["page"]) for x in e["evidence"]]))
            continue
        events.append(SimpleNamespace(financial_event_type=e["legacy_type"], title=e["event_type"], status=e["status"],
                                      evidence=[SimpleNamespace(page=x["page"]) for x in e["evidence"]]))
    return SimpleNamespace(fields=fields, events=events, unevaluated=[e["event_type"] for e in ev if not e["legacy_type"]])
