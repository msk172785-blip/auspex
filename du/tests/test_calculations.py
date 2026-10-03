from datetime import date
from decimal import Decimal

from du_engine import calculations as c


def test_add_months_clamps_end_of_month():
    assert c.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert c.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert c.add_months(date(2027, 1, 15), -2) == date(2026, 11, 15)


def test_next_anniversary_and_deadline_case_a():
    an = c.next_anniversary(date(2026, 1, 15), date(2026, 10, 3))
    assert an.value == date(2027, 1, 15)
    r = c.apply_deadline_rule({"amount": 2, "unit": "months", "direction": "before"}, an.value, "date anniversaire")
    assert r.value == date(2026, 11, 15)
    assert any("15/11/2026" in s for s in r.steps)


def test_deadline_without_reference_date_is_missing_not_guessed():
    r = c.apply_deadline_rule({"amount": 2, "unit": "months", "direction": "before"}, None, "date_notification")
    assert r.value is None
    assert r.missing_information == ["date_notification"]


def test_deadline_days_after():
    r = c.apply_deadline_rule({"amount": 30, "unit": "days", "direction": "after"}, date(2027, 1, 15), "x")
    assert r.value == date(2027, 2, 14)


def test_revision_delta_case_a():
    r = c.revision_delta(220000, Decimal("1.03"))
    assert r.value["new_annual_price"] == Decimal("226600.00")
    assert r.value["potential_delta"] == Decimal("6600.00")
    assert r.steps  # étapes affichées


def test_coefficient_from_formula_and_indices():
    r = c.revision_coefficient("P = P0 x (0,15 + 0,85 x I/I0)", 100, 103)
    assert r.value == Decimal("1.0255")  # 0,15 + 0,85 × 1,03


def test_coefficient_form_cn():
    r = c.revision_coefficient("Cn = 0,125 + 0,875 x (S/S0)", 200, 210)
    assert r.value == Decimal("1.0438")  # 0,125 + 0,875 × 1,05 = 1,04375 -> 1,0438


def test_multi_index_formula_is_not_guessed():
    assert c.parse_parametric_formula("P = P0 x (0,15 + 0,50 x A/A0 + 0,35 x B/B0)") is None
    r = c.revision_coefficient("P = P0 x (0,15 + 0,50 x A/A0 + 0,35 x B/B0)", 100, 103)
    assert r.value is None and r.missing_information


def test_missing_index_values_reported():
    r = c.revision_coefficient("P = P0 x (0,15 + 0,85 x I/I0)", None, None)
    assert r.value is None
    assert "valeur de l'indice de base I0" in r.missing_information


def test_threshold_blocks_and_cap_limits():
    r = c.revision_delta(100000, Decimal("1.005"), threshold_pct=1)
    assert r.value["threshold_blocked"] and r.value["potential_delta"] == 0
    r = c.revision_delta(100000, Decimal("1.08"), cap_pct=5)
    assert r.value["potential_delta"] == Decimal("5000.00")


def test_reconciliation_amounts():
    assert c.amendment_underbilling(31.40, 33.10, 1000).value == Decimal("1700.00")
    assert c.unbilled_amount(4800, 0).value == Decimal("4800.00")


def test_fmt_eur():
    assert c.fmt_eur(6600) == "6 600 €"
    assert c.fmt_eur(Decimal("1234.5")) == "1 234,50 €"
