"""RÉGRESSION sur real_001 (contrat de CONCEPTION, déjà connu).

Ce test n'est PAS une mesure de généralisation : il vérifie seulement que le moteur v1 continue de
retrouver les catégories identifiées dans le brouillon de vérité terrain (non validé) de real_001.
Un faux négatif sur une catégorie critique fait échouer ce test.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from du_engine.text_input import text_to_document
from du_engine.v1.engine import analyze_v1

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "data" / "contracts" / "real_001"


@pytest.fixture(scope="module")
def r():
    doc = text_to_document((CASE / "CCP_Lot1_Nettoyage_des_locaux_2026.txt").read_text(encoding="utf-8"),
                           "CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf")
    return analyze_v1([doc], reference_date=date(2026, 10, 3), contract_key="real_001")


def ev(r, t):
    return [e for e in r["events"] if e["event_type"] == t]


def test_ground_truth_stays_unvalidated():
    gt = json.loads((ROOT / "data" / "ground_truth" / "real_001.json").read_text(encoding="utf-8"))
    assert gt["validated"] is False


def test_not_simulated(r):
    assert r["SIMULATED_EXAMPLE"] is False


def test_revision_request_two_months_before_anniversary(r):
    dl = ev(r, "PRICE_REVISION_DEADLINE")
    assert any(d["deadline_rule"]["amount"] == 2 and d["deadline_rule"]["unit"] == "months"
               and d["deadline_rule"]["direction"] == "before" and d["deadline_rule"]["anchor"] == "ANNIVERSARY" for d in dl)
    assert all(d["actor"] == "SUPPLIER" for d in dl)
    assert any(d["attributes"].get("form") == "LETTRE_RECOMMANDEE_AR" for d in dl)


def test_explicit_supplier_actions(r):
    acts = ev(r, "SUPPLIER_ACTION_REQUIRED")
    assert any(a["actor_basis"] == "EXPLICIT" and "coefficient" in a["source_quote"] for a in acts)
    assert any("bordereau des prix unitaires" in a["source_quote"] for a in acts)


def test_consequence_if_deadline_missed(r):
    cons = [c for c in ev(r, "CONSEQUENCE_IF_NO_ACTION") if c["consequence_if_no_action"]["type"] == "PRICE_KEPT"]
    assert cons and cons[0]["consequence_if_no_action"]["polarity_for_supplier"] == "UNFAVORABLE"
    assert cons[0]["attributes"]["related_to"] == "PRICE_REVISION"
    assert cons[0]["trigger"] != "AUTOMATIC"
    assert not any(p["trigger"] == "AUTOMATIC" for p in ev(r, "PRICE_REVISION"))


def test_caps_annual_and_cumulative(r):
    pcts = {(p["value"], p["role"], p["subrole"]) for e in ev(r, "PRICE_REVISION_THRESHOLD") for p in e["percentages"]}
    assert (3.0, "CAP", "CAP_ANNUAL") in pcts
    assert (9.0, "CAP", "CAP_CUMULATIVE") in pcts
    assert not any(p[1] == "THRESHOLD" and p[0] in (3.0, 9.0) for p in pcts)


def test_purchase_orders_and_ceiling_not_contract_value(r):
    po = ev(r, "PURCHASE_ORDER_BILLING")
    assert po and any(a["value"] == 12000.0 and a["role"] == "PURCHASE_ORDER_ANNUAL_CEILING" for a in po[0]["amounts"])
    assert r["contract"]["annual_contract_value"] is None


def test_invoice_deemed_accepted_after_30_days(r):
    cons = [c for c in ev(r, "CONSEQUENCE_IF_NO_ACTION") if c["consequence_if_no_action"]["type"] == "DEEMED_ACCEPTED"
            and c["consequence_if_no_action"]["polarity_for_supplier"] == "UNFAVORABLE"]
    assert cons and cons[0]["deadline_rule"]["amount"] == 30 and cons[0]["deadline_rule"]["unit"] == "days"


def test_new_prices_tacitly_accepted_is_favorable(r):
    fav = [c for c in ev(r, "CONSEQUENCE_IF_NO_ACTION") if c["consequence_if_no_action"]["type"] == "DEEMED_ACCEPTED"
           and c["consequence_if_no_action"]["polarity_for_supplier"] == "FAVORABLE"]
    assert fav and fav[0]["actor"] == "BUYER"


def test_max_duration(r):
    d = r["contract"]["duration"]
    assert d["initial_months"] == 12 and d["max_months"] == 45 and d["stated_max_months"] == 48
    assert d["stated_last_date"] == "2030-09-15" == d["computed_last_date_from_earliest_start"]


def test_conditional_start_date(r):
    st = r["contract"]["start_date"]
    assert st["expression"] == "max(2026-12-16, notification_date)"
    assert st["value"] is None and st["earliest"] == "2026-12-16" and "notification_date" in st["missing"]


def test_payment_term(r):
    pt = ev(r, "PAYMENT_TERM")
    assert pt and pt[0]["deadline_rule"]["amount"] == 30 and pt[0]["deadline_rule"]["unit"] == "days"


def test_reexamination_clause(r):
    rx = ev(r, "REEXAMINATION_RIGHT")
    assert rx and any(p["value"] == 80.0 and p["subrole"] == "COST_SHARE" for p in rx[0]["percentages"])


def test_new_price_elements(r):
    pr = ev(r, "PRICE_REVISION")
    assert len(pr) == 1
    a = pr[0]["attributes"]
    assert a["formula"].replace(" ", "") == "P=P0(BtoB/BtoB0)"
    assert "010766785" in a["index_identifiers"]
    assert a["revision_frequency"] == "ANNUAL"          # et non une fréquence opérationnelle
    assert a.get("first_period_firm") is True
    assert "facturation" in a.get("application_timing", "")


def test_billing_condition(r):
    bc = ev(r, "BILLING_CONDITION")
    assert bc and all("procès-verbal" in b["source_quote"] for b in bc)


def test_article_attribution_page_7(r):
    dl = ev(r, "PRICE_REVISION_DEADLINE")[0]
    assert dl["source_article"] == "4.3" and dl["source_page"] == 7


def test_every_live_evidence_is_exact_and_critical_needs_review(r):
    for e in r["events"]:
        assert all(x["match"] in ("EXACT", "EXACT_OTHER_PAGE", "FUZZY") for x in e["evidence"])
        assert e["status"] != "VALIDATED"
        if e["critical"]:
            assert e["human_review_required"] is True
    assert all(v["outcome"] in ("FOUND", "NOT_FOUND", "REVIEW_REQUIRED") for v in r["critical_checklist"].values())


def test_document_anomalies_reported(r):
    a = " ".join(r["document_anomalies"])
    assert "4.3 utilisé 2 fois" in a and "4.2.1" in a
