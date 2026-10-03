from datetime import date
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from du_engine.corpus import analyze_case
from du_engine.extractor import verify_quote
from du_engine.models import FACT, VALIDATED
from du_engine.pipeline import analyze_pdfs

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "simulated"
CORPUS = ROOT / "data" / "contracts"


@pytest.fixture(scope="module")
def case_a():
    return analyze_case(SIM / "case_A")


def test_case_a_revision_clause_with_evidence(case_a):
    f = case_a.fields
    assert f["revision_exists"].value is True
    assert f["revision_formula"].value == "P = P0 x (0,15 + 0,85 x I/I0)"
    assert f["deadline_rule"].value["amount"] == 2
    assert f["deadline_rule"].value["unit"] == "months"
    assert f["deadline_rule"].value["direction"] == "before"
    assert f["supplier_action_required"].value is True
    assert f["forfeiture_exists"].value is True
    ev = f["forfeiture_exists"].evidence[0]
    assert ev.page == 3 and ev.article == "4.3" and ev.quote_verified
    assert "À défaut de demande" in ev.quote


def test_case_a_event_matches_spec(case_a):
    e = case_a.events[0]
    assert e.financial_event_type == "PRICE_REVISION_FORFEITURE"
    assert e.severity == "critical"
    assert e.calculated_deadline == "2026-11-15"
    assert e.potential_amount == 6600.0
    assert e.financial_calculation["new_annual_price"] == 226600.0
    assert e.SIMULATED_EXAMPLE is True


def test_every_fact_has_verified_evidence(case_a):
    for name, f in case_a.fields.items():
        if f.kind == FACT:
            assert f.evidence, name
            assert all(e.quote_verified for e in f.evidence), name
            assert all(e.document and e.page >= 1 for e in f.evidence), name


def test_engine_never_outputs_validated():
    for case in sorted(CORPUS.iterdir()):
        if not case.is_dir():
            continue
        a = analyze_case(case)
        assert all(f.status != VALIDATED for f in a.fields.values())
        assert all(e.status != VALIDATED for e in a.events)


def test_missing_start_date_gives_review_required_not_a_guess():
    a = analyze_pdfs([SIM / "case_A" / "CCAP_SIM_A_nettoyage.pdf"], user_inputs={}, reference_date=date(2026, 10, 3))
    assert a.fields["contract_start_date"].value is None
    assert "date_notification" in a.fields["contract_start_date"].missing_information
    dl = [e for e in a.events if e.financial_event_type == "PRICE_REVISION_DEADLINE"][0]
    assert dl.calculated_deadline is None
    assert dl.status == "REVIEW_REQUIRED"
    assert any("date_notification" in m for m in dl.missing_information)
    # pas de montant annuel saisi -> pas d'impact inventé
    assert all(e.potential_amount is None for e in a.events)


def test_firm_prices_no_revision_event():
    a = analyze_case(CORPUS / "sim_005")
    assert a.fields["revision_exists"].value is False
    assert not [e for e in a.events if e.financial_event_type.startswith("PRICE_REVISION")]


def test_automatic_revision_has_no_supplier_action():
    a = analyze_case(CORPUS / "sim_006")
    assert a.fields["supplier_action_required"].value is False
    assert a.fields["threshold_value"].value == {"pct": 1.0, "kind": "DECLENCHEMENT"}


def test_multi_index_formula_flagged_for_review():
    a = analyze_case(CORPUS / "sim_007")
    assert a.fields["revision_formula"].status == "REVIEW_REQUIRED"
    assert a.fields["deadline_rule"].value["direction"] == "after"


def test_negated_retention_and_advance(case_a):
    assert case_a.fields["retention_exists"].value is False
    assert case_a.fields["advance_payment"].value is False


def test_pdf_without_text_layer(tmp_path):
    p = tmp_path / "scan.pdf"
    cv = canvas.Canvas(str(p))
    cv.rect(100, 100, 300, 300, fill=1)
    cv.showPage()
    cv.save()
    a = analyze_pdfs([p], reference_date=date(2026, 10, 3))
    assert a.events == []
    assert any("scanné" in w for w in a.warnings)
    assert all(not f.found or f.kind != FACT for f in a.fields.values())


def test_verify_quote_rejects_invented_text():
    page = "Les prix sont révisables annuellement.\nLe titulaire doit transmettre sa demande."
    assert verify_quote("Les prix sont révisables annuellement. Le titulaire doit", page)
    assert not verify_quote("Les prix sont fermes.", page)


@pytest.mark.xfail(strict=True, reason="Limite connue : vocabulaire « ajustement » non couvert par les règles (sim_008).")
def test_known_limit_off_vocabulary_revision():
    a = analyze_case(CORPUS / "sim_008")
    assert a.fields["revision_exists"].value is True
