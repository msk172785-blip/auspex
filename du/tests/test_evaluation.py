import json
from pathlib import Path

from du_engine.evaluation import aggregate, compare_events, error_list
from du_engine.models import ContractAnalysis, Evidence, FinancialEvent

ROOT = Path(__file__).resolve().parents[1]


def _analysis(types):
    evs = [FinancialEvent(financial_event_type=t, severity="info", title=t, contractual_fact={}, financial_calculation=None,
                          evidence=[Evidence("x.pdf", 3, None, "q", True)], confidence=0.9, status="AUTO_EXTRACTED")
           for t in types]
    return ContractAnalysis("c", [], {}, evs, {}, [], "2026-10-03")


def test_event_matching_tp_fp_fn():
    r = compare_events([{"type": "PRICE_REVISION", "page": 3}, {"type": "PRICE_REVISION_DEADLINE", "page": 3}],
                       _analysis(["PRICE_REVISION", "FINAL_BALANCE"]))
    assert len(r["tp"]) == 1 and len(r["fp"]) == 1 and len(r["fn"]) == 1
    assert r["fn"][0]["critical"] is True


def test_aggregate_weighted_recall_penalises_deadline_misses():
    res = [{"contract_id": "c", "SIMULATED_EXAMPLE": True, "fields": [], "expected_events": 2, "detected_events": 1,
            "events": compare_events([{"type": "PRICE_REVISION"}, {"type": "PRICE_REVISION_FORFEITURE"}],
                                     _analysis(["PRICE_REVISION"]))}]
    agg = aggregate(res)
    assert agg["recall"] == 0.5
    assert agg["weighted_recall"] == 0.25  # 1 / (1 + 3)
    assert agg["critical_false_negatives"] == 1
    assert any("FN CRITIQUE" in e for e in error_list(res))


def test_run_evaluation_cli(capsys):
    import run_evaluation
    assert run_evaluation.main(["--no-fail"]) == 0
    out = capsys.readouterr().out
    for label in ("Nombre de contrats", "True positives", "False negatives", "Recall", "Precision", "Liste exacte des erreurs"):
        assert label in out


def test_ground_truth_files_are_wellformed():
    for p in (ROOT / "data" / "ground_truth").glob("*.json"):
        gt = json.loads(p.read_text(encoding="utf-8"))
        assert "contract_id" in gt and "fields" in gt and "events" in gt


def test_critical_false_negative_fails_evaluation(capsys):
    """Un faux négatif critique doit produire un code de sortie non nul (sauf --no-fail)."""
    import run_evaluation
    code = run_evaluation.main([])
    out = capsys.readouterr().out
    has_crit = "ÉCHEC" in out
    assert code == (1 if has_crit else 0)
