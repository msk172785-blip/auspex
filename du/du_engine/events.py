"""Transformation des champs extraits en événements économiques.

Chaque événement sépare :
  contractual_fact       (A) faits issus du contrat, avec preuves
  financial_calculation  (B) calculs déterministes, avec étapes
  assumptions / missing_information (C) hypothèses explicites et informations manquantes
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from . import calculations as calc
from .models import (AUTO_EXTRACTED, CALCULATION, REVIEW_REQUIRED, ExtractedField, FinancialEvent)


def _status(fields: list[Optional[ExtractedField]], missing: list[str]) -> str:
    if missing:
        return REVIEW_REQUIRED
    for f in fields:
        if f is None or f.status != AUTO_EXTRACTED:
            return REVIEW_REQUIRED
    return AUTO_EXTRACTED


def _conf(fields: list[Optional[ExtractedField]]) -> float:
    vals = [f.confidence for f in fields if f is not None and f.found]
    return round(min(vals), 2) if vals else 0.0


def _ev(*fields: Optional[ExtractedField]):
    out, seen = [], set()
    for f in fields:
        if f is None:
            continue
        for e in f.evidence:
            k = (e.document, e.page, e.quote)
            if k not in seen:
                seen.add(k)
                out.append(e)
    return out


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


def _severity_for_deadline(deadline: Optional[date], ref: date, forfeiture: bool) -> str:
    if deadline is None:
        return "high" if forfeiture else "medium"
    days = (deadline - ref).days
    if days < 0:
        return "high"
    if days <= 60 or (forfeiture and days <= 120):
        return "critical"
    if days <= 120:
        return "high"
    return "medium"


def build_events(fields: dict[str, ExtractedField], amendments: dict[str, list], user: dict,
                 recon: dict, reference_date: date, simulated: bool = False) -> tuple[list[FinancialEvent], dict[str, ExtractedField]]:
    """Retourne les événements et les champs calculés (contract_end_date, calculated_deadline)."""
    ev: list[FinancialEvent] = []
    F = fields.get

    start = _parse_date((F("contract_start_date").value if F("contract_start_date") and F("contract_start_date").found else None))
    annual = F("annual_amount").value if F("annual_amount") and F("annual_amount").found else None

    # ---- fin de contrat (calcul)
    dur = F("contract_duration")
    if start and dur and dur.found and isinstance(dur.value, dict):
        months = dur.value.get("max_months") or dur.value.get("initial_months")
        r = calc.contract_end(start, months)
        fields["contract_end_date"] = ExtractedField(
            name="contract_end_date", value=r.value.isoformat(), kind=CALCULATION, evidence=_ev(dur),
            confidence=_conf([dur, F("contract_start_date")]), status=REVIEW_REQUIRED,
            notes=r.steps + ["Fin calculée en supposant toutes les reconductions exercées." if dur.value.get("max_months") else ""])
    end = _parse_date(fields["contract_end_date"].value) if fields.get("contract_end_date") and fields["contract_end_date"].found else None

    # ---- révision : calcul d'impact
    rev = F("revision_exists")
    revision_calc = None
    rev_missing: list[str] = []
    if rev and rev.value is True:
        formula = F("revision_formula").value if F("revision_formula") and F("revision_formula").found else None
        coef = calc.revision_coefficient(formula, user.get("index_base"), user.get("index_new"),
                                         user.get("revision_coefficient"))
        thr = F("threshold_value")
        # Seul un seuil de déclenchement bloque le calcul ; butoir/sauvegarde restent signalés pour revue humaine.
        thr_pct = thr.value["pct"] if thr and thr.found and thr.value.get("kind") == "DECLENCHEMENT" else None
        cap = F("cap_value")
        cap_pct = cap.value if cap and cap.found else None
        if annual is None:
            rev_missing.append("montant annuel")
        rev_missing += coef.missing_information
        if coef.value is not None and annual is not None:
            revision_calc = calc.revision_delta(annual, coef.value, thr_pct, cap_pct)
            revision_calc.steps = coef.steps + revision_calc.steps
        facts = {"revision_exists": True,
                 "price_type": F("price_type").value if F("price_type") else None,
                 "revision_formula": formula,
                 "revision_index": F("revision_index").value if F("revision_index") else None,
                 "revision_frequency": F("revision_frequency").value if F("revision_frequency") else None}
        fc = None
        if revision_calc:
            v = revision_calc.to_dict()["value"]
            fc = {**v, "steps": revision_calc.steps}
        assumptions = []
        if user.get("revision_coefficient") is not None:
            assumptions.append("Coefficient de révision saisi par l'utilisateur, non vérifié par DÛ contre les indices publiés.")
        if user.get("index_new") is not None:
            assumptions.append("Valeurs d'indices saisies par l'utilisateur (DÛ ne télécharge pas les indices INSEE).")
        ev.append(FinancialEvent(
            financial_event_type="PRICE_REVISION", severity="medium",
            title="Révision de prix prévue au contrat",
            contractual_fact=facts, financial_calculation=fc,
            evidence=_ev(rev, F("revision_formula"), F("revision_index")),
            confidence=_conf([rev, F("revision_formula")]), status=_status([rev], rev_missing),
            action="Vérifier l'indice publié, calculer le coefficient et préparer la demande de révision.",
            missing_information=rev_missing, assumptions=assumptions,
            potential_amount=float(fc["potential_delta"]) if fc else None, SIMULATED_EXAMPLE=simulated))

    # ---- échéance de demande de révision
    sar, dl = F("supplier_action_required"), F("deadline_rule")
    deadline: Optional[date] = None
    dl_steps: list[str] = []
    dl_missing: list[str] = []
    dl_assumptions: list[str] = []
    if (sar and sar.value is True) or (dl and dl.found):
        rule = dl.value if dl and dl.found else None
        if rule is None:
            dl_missing.append("règle de délai (non trouvée dans le contrat)")
        elif rule.get("reference") == "anniversary":
            if start is None:
                dl_missing.append("date_notification / date de début du contrat")
                dl_steps.append("Date anniversaire inconnue : la date de début (ou de notification) n'est pas connue.")
            else:
                dl_assumptions.append("Date anniversaire calculée à partir de la date de début renseignée. "
                                      "Vérifier que le contrat définit l'anniversaire sur cette même date (notification vs début d'exécution).")
                an = calc.next_anniversary(start, reference_date, end)
                dl_steps += an.steps
                if an.value is None:
                    dl_missing += an.missing_information
                else:
                    r = calc.apply_deadline_rule(rule, an.value, "date anniversaire")
                    dl_steps += r.steps
                    deadline = r.value
                    dl_missing += r.missing_information
        elif rule.get("reference") == "notification":
            nd = _parse_date(user.get("notification_date"))
            r = calc.apply_deadline_rule(rule, nd, "date de notification")
            dl_steps += r.steps
            deadline, dl_missing = r.value, dl_missing + r.missing_information
        else:
            dl_missing.append(f"date de référence « {rule.get('reference')} »")
            dl_steps.append(f"Référence de délai non gérée automatiquement : {rule.get('text')}")
        if deadline:
            fields["calculated_deadline"] = ExtractedField(
                name="calculated_deadline", value=deadline.isoformat(), kind=CALCULATION, evidence=_ev(dl),
                confidence=_conf([dl]), status=_status([dl], dl_missing), notes=dl_steps,
                missing_information=dl_missing)
        else:
            fields["calculated_deadline"] = ExtractedField(
                name="calculated_deadline", value=None, kind="MISSING", evidence=_ev(dl), status=REVIEW_REQUIRED,
                notes=dl_steps, missing_information=dl_missing)
        forfeit = bool(F("forfeiture_exists") and F("forfeiture_exists").value is True)
        sev = _severity_for_deadline(deadline, reference_date, forfeit)
        days_left = (deadline - reference_date).days if deadline else None
        title = "Demande de révision : échéance"
        if days_left is not None and days_left < 0:
            title = "Échéance de demande de révision dépassée pour cette période"
        ev.append(FinancialEvent(
            financial_event_type="PRICE_REVISION_DEADLINE", severity=sev, title=title,
            contractual_fact={"supplier_action_required": sar.value if sar else None,
                              "supplier_action_description": F("supplier_action_description").value if F("supplier_action_description") else None,
                              "deadline_rule": rule.get("text") if rule else None},
            financial_calculation={"calculated_deadline": deadline.isoformat() if deadline else None,
                                   "days_left": days_left, "steps": dl_steps},
            evidence=_ev(sar, dl), confidence=_conf([sar, dl]), status=_status([sar, dl], dl_missing),
            action="Envoyer la demande de révision (courrier/plateforme) avec le calcul et le nouveau BPU avant l'échéance.",
            missing_information=dl_missing, assumptions=dl_assumptions,
            calculated_deadline=deadline.isoformat() if deadline else None,
            potential_amount=revision_calc.to_dict()["value"]["potential_delta"] if revision_calc else None,
            SIMULATED_EXAMPLE=simulated))

    # ---- forclusion
    ff = F("forfeiture_exists")
    if ff and ff.value is True:
        cons = F("forfeiture_consequence")
        miss = list(dl_missing) + ([m for m in rev_missing if m not in dl_missing] if rev and rev.value else [])
        fc = None
        if revision_calc:
            v = revision_calc.to_dict()["value"]
            fc = {**v, "steps": revision_calc.steps + dl_steps}
        ev.append(FinancialEvent(
            financial_event_type="PRICE_REVISION_FORFEITURE", severity="critical",
            title="Révision tarifaire à demander — perte du droit en cas d'oubli",
            contractual_fact={"supplier_action_required": sar.value if sar else None,
                              "deadline_rule": dl.value.get("text") if dl and dl.found else None,
                              "forfeiture": True,
                              "forfeiture_consequence": cons.value if cons else None},
            financial_calculation=fc, evidence=_ev(ff, dl, sar),
            confidence=_conf([ff, dl, sar]), status=_status([ff, dl, sar], miss),
            action="Envoyer demande + calcul + nouveau BPU avant l'échéance ; conserver la preuve d'envoi.",
            missing_information=miss, assumptions=dl_assumptions,
            calculated_deadline=deadline.isoformat() if deadline else None,
            potential_amount=float(fc["potential_delta"]) if fc else None, SIMULATED_EXAMPLE=simulated))

    # ---- seuil / plafond
    te, ce = F("threshold_exists"), F("cap_exists")
    if (te and te.value is True) or (ce and ce.value is True):
        tv, cv = F("threshold_value"), F("cap_value")
        ev.append(FinancialEvent(
            financial_event_type="PRICE_REVISION_THRESHOLD", severity="medium",
            title="Seuil ou plafond conditionnant la révision",
            contractual_fact={"threshold": tv.value if tv and tv.found else None, "cap_pct": cv.value if cv and cv.found else None},
            financial_calculation=None, evidence=_ev(tv, cv),
            confidence=_conf([tv, cv]), status=_status([f for f in (tv, cv) if f and f.found], []),
            action="Vérifier si la variation d'indice franchit le seuil avant de demander (ou si le plafond limite le gain).",
            SIMULATED_EXAMPLE=simulated))

    # ---- avenants (P2)
    invoices = recon.get("invoices", [])
    for doc, changes in amendments.items():
        for ch in changes:
            facts = {k: v for k, v in ch.items() if k != "evidence"}
            fc, miss, amount, sev = None, [], None, "medium"
            if ch["effective_date"] is None:
                miss.append("date d'effet de l'avenant")
            if not invoices:
                miss.append("factures (pour vérifier l'application du nouveau prix)")
            else:
                eff = _parse_date(ch["effective_date"])
                qty, lines = 0, []
                for inv in invoices:
                    idate = _parse_date(inv.get("date"))
                    for ln in inv.get("lines", []):
                        same_item = (ch["item_code"] and ln.get("item_code") == ch["item_code"])
                        if not same_item:
                            continue
                        if eff and idate and idate >= eff and calc.D(ln["unit_price"]) == calc.D(ch["old_unit_price"]):
                            qty += calc.D(ln["quantity"])
                            lines.append(f"{inv['invoice_id']} ({inv['date']}) : {ln['quantity']} × {ln['unit_price']} €")
                if qty:
                    r = calc.amendment_underbilling(ch["old_unit_price"], ch["new_unit_price"], qty)
                    fc = {"underbilled_amount": float(r.value), "lines": lines, "steps": r.steps}
                    amount, sev = float(r.value), "high"
                elif ch["item_code"] is None:
                    miss.append("code article de l'avenant (rapprochement impossible)")
            ev.append(FinancialEvent(
                financial_event_type="AMENDMENT_PRICE_CHANGE", severity=sev,
                title="Avenant : nouveau prix unitaire" + (" facturé à l'ancien prix" if amount else ""),
                contractual_fact=facts, financial_calculation=fc, evidence=[ch["evidence"]],
                confidence=0.85 if ch["evidence"].quote_verified else 0.5,
                status=REVIEW_REQUIRED if miss or not ch["evidence"].quote_verified else AUTO_EXTRACTED,
                action="Émettre une facture complémentaire pour l'écart constaté." if amount else
                       "Vérifier que les factures postérieures à la date d'effet appliquent le nouveau prix.",
                missing_information=miss, potential_amount=amount, SIMULATED_EXAMPLE=simulated))

    # ---- bons de commande
    po = F("purchase_orders_exist")
    pos = recon.get("purchase_orders", [])
    if (po and po.value is True) or pos:
        billed_refs = {}
        for inv in invoices:
            for ln in inv.get("lines", []):
                if ln.get("po_ref"):
                    billed_refs[ln["po_ref"]] = billed_refs.get(ln["po_ref"], calc.D(0)) + calc.D(ln.get("amount") or calc.D(ln["unit_price"]) * calc.D(ln["quantity"]))
        flagged = False
        for p in pos:
            if p.get("status") != "REALISEE":
                continue
            billed = billed_refs.get(p["po_id"], calc.D(0))
            if billed < calc.D(p["amount"]):
                r = calc.unbilled_amount(p["amount"], billed)
                flagged = True
                ev.append(FinancialEvent(
                    financial_event_type="PURCHASE_ORDER_BILLING", severity="high",
                    title=f"Bon de commande {p['po_id']} réalisé, non (entièrement) facturé",
                    contractual_fact={"purchase_order": p, "contract_mentions_purchase_orders": po.value if po else None},
                    financial_calculation={"unbilled_amount": float(r.value), "steps": r.steps +
                                           [f"Recherche : lignes de facture portant la référence {p['po_id']}."]},
                    evidence=_ev(po), confidence=_conf([po]) if po else 0.6, status=REVIEW_REQUIRED,
                    action="Vérifier l'attestation de service fait, puis facturer le bon de commande.",
                    missing_information=[] if invoices else ["factures"],
                    assumptions=["Rapprochement par référence de bon de commande uniquement : une facture sans référence BC ne sera pas reconnue."],
                    potential_amount=float(r.value), SIMULATED_EXAMPLE=simulated))
        if po and po.value is True and not flagged:
            ev.append(FinancialEvent(
                financial_event_type="PURCHASE_ORDER_BILLING", severity="info",
                title="Marché exécuté par bons de commande",
                contractual_fact={"purchase_orders_exist": True}, financial_calculation=None,
                evidence=_ev(po), confidence=po.confidence, status=_status([po], []),
                action="Contrôler que chaque bon de commande exécuté a été facturé (fournir BC + factures pour le rapprochement).",
                missing_information=[] if pos else ["liste des bons de commande"], SIMULATED_EXAMPLE=simulated))

    vs = F("variable_services_exist")
    if vs and vs.value is True:
        ev.append(FinancialEvent(
            financial_event_type="VARIABLE_SERVICE_BILLING", severity="info",
            title="Prestations variables / au bordereau de prix",
            contractual_fact={"variable_services_exist": True}, financial_calculation=None,
            evidence=_ev(vs), confidence=vs.confidence, status=_status([vs], []),
            action="Vérifier que les quantités réellement exécutées sont toutes facturées.", SIMULATED_EXAMPLE=simulated))

    # ---- retenue de garantie
    rt = F("retention_exists")
    if rt and rt.value is True:
        rr, gp = F("retention_release_rule"), F("guarantee_period_months")
        ledger = recon.get("retention") or {}
        fc, miss, amount, sev, assumptions = None, [], None, "medium", []
        retained = sum((calc.D(x["amount"]) for x in ledger.get("retained", [])), calc.D(0))
        released = sum((calc.D(x["amount"]) for x in ledger.get("payments", []) if x.get("type") == "RETENTION_RELEASE"), calc.D(0))
        reception = _parse_date(ledger.get("reception_date"))
        months_after = None
        if rr and rr.found:
            m = re.search(r"(\d+|un|une|deux|trois|six)\s+mois\s+apr[eè]s\s+l'expiration\s+du\s+d[ée]lai\s+de\s+garantie", rr.value, re.I)
            if m:
                from .extractor import to_int
                months_after = to_int(m.group(1))
        if not ledger:
            miss.append("montants retenus et règlements (pour vérifier la libération)")
        else:
            if reception is None:
                miss.append("date de réception")
            if not (gp and gp.found):
                miss.append("délai de garantie")
            if months_after is None:
                miss.append("délai de remboursement après fin de garantie (règle non interprétée)")
            steps = [f"Montant total retenu = {calc.fmt_eur(retained)}", f"Montant déjà libéré = {calc.fmt_eur(released)}"]
            due = None
            if not miss:
                end_g = calc.add_months(reception, gp.value)
                due = calc.add_months(end_g, months_after)
                steps += [f"Fin du délai de garantie = {calc.fmt_date(reception)} + {gp.value} mois = {calc.fmt_date(end_g)}",
                          f"Libération exigible = {calc.fmt_date(end_g)} + {months_after} mois = {calc.fmt_date(due)}"]
            outstanding = calc.money(retained - released)
            steps.append(f"Reste à libérer = {calc.fmt_eur(retained)} − {calc.fmt_eur(released)} = {calc.fmt_eur(outstanding)}")
            condition_met = due is not None and due <= reference_date
            if due:
                steps.append(f"Condition de libération atteinte au {calc.fmt_date(reference_date)} : {'oui' if condition_met else 'non'}")
            fc = {"retained": float(retained), "released": float(released), "outstanding": float(outstanding),
                  "release_due_date": due.isoformat() if due else None, "condition_met": condition_met, "steps": steps}
            if condition_met and outstanding > 0:
                amount, sev = float(outstanding), "high"
            assumptions.append("Les réserves éventuelles à la réception ne sont pas prises en compte (non fournies).")
        ev.append(FinancialEvent(
            financial_event_type="RETENTION_RELEASE", severity=sev,
            title="Retenue de garantie à récupérer" if amount else "Retenue de garantie : libération à suivre",
            contractual_fact={"retention_exists": True,
                              "retention_rate_pct": F("retention_rate").value if F("retention_rate") else None,
                              "release_rule": rr.value if rr and rr.found else None,
                              "guarantee_period_months": gp.value if gp and gp.found else None},
            financial_calculation=fc, evidence=_ev(rt, F("retention_rate"), rr, gp),
            confidence=_conf([rt, rr]), status=_status([rt, rr], miss),
            action="Demander la restitution de la retenue (ou la mainlevée de la garantie) à l'acheteur." if amount else
                   "Suivre la date de libération de la retenue de garantie.",
            missing_information=miss, assumptions=assumptions, potential_amount=amount,
            calculated_deadline=fc["release_due_date"] if fc else None, SIMULATED_EXAMPLE=simulated))

    fb = F("final_balance_rule")
    if fb and fb.found:
        ev.append(FinancialEvent(
            financial_event_type="FINAL_BALANCE", severity="medium", title="Solde / décompte final du marché",
            contractual_fact={"final_balance_rule": fb.value}, financial_calculation=None, evidence=_ev(fb),
            confidence=fb.confidence, status=_status([fb], []),
            action="Préparer le projet de décompte final dans le délai prévu.", SIMULATED_EXAMPLE=simulated))

    for key, title, action in [
        ("late_payment_interest", "Intérêts moratoires en cas de retard de paiement",
         "Vérifier les dates de paiement ; réclamer intérêts moratoires et indemnité forfaitaire si retard."),
        ("advance_payment", "Avance prévue au marché", "Vérifier que l'avance a été demandée et versée."),
    ]:
        f = F(key)
        if f and f.value is True:
            pt = F("payment_terms")
            ev.append(FinancialEvent(
                financial_event_type="OTHER_FINANCIAL_RIGHT", severity="info", title=title,
                contractual_fact={key: True, "payment_terms": pt.value if pt and pt.found else None},
                financial_calculation=None, evidence=_ev(f, pt if key == "late_payment_interest" else None),
                confidence=f.confidence, status=_status([f], []), action=action, SIMULATED_EXAMPLE=simulated))

    order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    type_rank = {"PRICE_REVISION_FORFEITURE": 0, "PRICE_REVISION_DEADLINE": 1}
    ev.sort(key=lambda e: (order.get(e.severity, 9), -(e.potential_amount or 0), type_rank.get(e.financial_event_type, 5)))
    return ev, fields
