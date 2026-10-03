from pathlib import Path

import pytest

from du_engine.corpus import analyze_case

SIM = Path(__file__).resolve().parents[1] / "data" / "simulated"


@pytest.mark.parametrize("case,etype,amount", [
    ("case_A", "PRICE_REVISION_FORFEITURE", 6600.0),
    ("case_B", "AMENDMENT_PRICE_CHANGE", 1700.0),
    ("case_C", "PURCHASE_ORDER_BILLING", 4800.0),
    ("case_D", "RETENTION_RELEASE", 12500.0),
])
def test_simulated_case_amounts(case, etype, amount):
    a = analyze_case(SIM / case)
    assert a.SIMULATED_EXAMPLE is True
    ev = [e for e in a.events if e.financial_event_type == etype and e.potential_amount]
    assert ev, [e.financial_event_type for e in a.events]
    assert ev[0].potential_amount == amount
    assert ev[0].SIMULATED_EXAMPLE is True
    assert ev[0].financial_calculation["steps"]


def test_case_b_only_counts_invoices_after_effective_date():
    a = analyze_case(SIM / "case_B")
    e = [e for e in a.events if e.financial_event_type == "AMENDMENT_PRICE_CHANGE"][0]
    assert e.contractual_fact["effective_date"] == "2026-03-01"
    assert len(e.financial_calculation["lines"]) == 2  # la facture de février est exclue


def test_case_c_ignores_invoiced_and_ongoing_orders():
    a = analyze_case(SIM / "case_C")
    po = [e for e in a.events if e.financial_event_type == "PURCHASE_ORDER_BILLING"]
    assert len(po) == 1 and "BC-SIM-2026-014" in po[0].title


def test_case_d_release_date():
    a = analyze_case(SIM / "case_D")
    e = [e for e in a.events if e.financial_event_type == "RETENTION_RELEASE"][0]
    assert e.financial_calculation["release_due_date"] == "2026-07-30"
    assert e.financial_calculation["condition_met"] is True
