"""Évalue DÛ sur tous les contrats disposant d'une vérité terrain validée.

Usage :
    python run_evaluation.py                 # moteur hybride v1 (défaut), contrats avec ground truth validé
    python run_evaluation.py --engine baseline   # ancien moteur regex (comparaison)
    python run_evaluation.py --real-only     # exclut les contrats simulés
    python run_evaluation.py --json          # sortie JSON brute

Les résultats détaillés sont écrits dans data/results/evaluation_<horodatage>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from du_engine.corpus import analyze_case, load_case  # noqa: E402
from du_engine.pdf_reader import read_pdf  # noqa: E402
from du_engine.v1.engine import analyze_v1, legacy_view  # noqa: E402
from du_engine.evaluation import aggregate, error_list, evaluate_contract  # noqa: E402

CONTRACTS = ROOT / "data" / "contracts"
GROUND_TRUTH = ROOT / "data" / "ground_truth"
RESULTS = ROOT / "data" / "results"


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f} %"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real-only", action="store_true", help="exclure les contrats SIMULATED_EXAMPLE")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", choices=["v1", "baseline"], default="v1")
    ap.add_argument("--no-fail", action="store_true", help="ne pas renvoyer de code d'erreur sur faux négatif critique")
    args = ap.parse_args(argv)

    gts = []
    skipped = []
    for p in sorted(GROUND_TRUTH.glob("*.json")):
        if p.name.startswith("_"):
            continue
        gt = json.loads(p.read_text(encoding="utf-8"))
        if not gt.get("validated"):
            skipped.append(f"{p.name} (validated=false)")
            continue
        if args.real_only and gt.get("SIMULATED_EXAMPLE"):
            continue
        cid = gt["contract_id"]
        case = CONTRACTS / cid if (CONTRACTS / cid).is_dir() else CONTRACTS / f"{cid}.pdf"
        if not case.exists():
            skipped.append(f"{p.name} (aucun document dans data/contracts/{cid})")
            continue
        gts.append((gt, case))

    results = []
    RESULTS.mkdir(parents=True, exist_ok=True)
    unevaluated = {}
    for gt, case in gts:
        if args.engine == "baseline":
            analysis = analyze_case(case)
            raw = analysis.to_dict()
        else:
            c = load_case(case)
            meta = c["meta"]
            from datetime import date as _d
            raw = analyze_v1([read_pdf(p) for p in c["pdfs"]], user_inputs=meta.get("user_inputs", {}), recon=c["recon"],
                             reference_date=_d.fromisoformat(meta["reference_date"]) if meta.get("reference_date") else None,
                             simulated=bool(meta.get("SIMULATED_EXAMPLE")), contract_key=c["key"])
            analysis = legacy_view(raw)
            unevaluated[gt["contract_id"]] = analysis.unevaluated
        (RESULTS / f"{gt['contract_id']}_{args.engine}_analysis.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        results.append(evaluate_contract(analysis, gt))

    agg = aggregate(results)
    errors = error_list(results)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {"engine": args.engine, "summary": agg, "errors": errors, "skipped": skipped, "details": results,
           "events_outside_ground_truth_schema": unevaluated}
    (RESULTS / f"evaluation_{stamp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    print("=" * 72)
    print(f"DÛ — ÉVALUATION SUR VÉRITÉ TERRAIN — moteur {args.engine}")
    print("=" * 72)
    if agg["simulated_contracts"]:
        print(f"ATTENTION : {agg['simulated_contracts']}/{agg['contracts']} contrats sont des EXEMPLES SIMULÉS rédigés par "
              "l'auteur des règles.\nCes scores ne mesurent pas la performance sur de vrais contrats.")
    print(f"Nombre de contrats            : {agg['contracts']}")
    print(f"Événements attendus           : {agg['expected_events']}")
    print(f"Événements détectés           : {agg['detected_events']}")
    print(f"True positives                : {agg['true_positives']}")
    print(f"False positives               : {agg['false_positives']}")
    print(f"False negatives               : {agg['false_negatives']}  (dont CRITIQUES, à échéance : {agg['critical_false_negatives']})")
    print(f"Recall                        : {pct(agg['recall'])}")
    print(f"Recall pondéré (échéances ×3) : {pct(agg['weighted_recall'])}")
    print(f"Precision                     : {pct(agg['precision'])}")
    print(f"Page source correcte (TP)     : {pct(agg['event_page_accuracy'])}")
    print("-" * 72)
    print("Exactitude par champ :")
    labels = {"revision_exists": "présence d'une révision", "revision_formula": "formule", "revision_index": "indice",
              "deadline_rule": "deadline (règle)", "supplier_action_required": "action fournisseur",
              "forfeiture_exists": "forclusion", "threshold_exists": "seuil", "revision_source_page": "page/source"}
    for k, v in agg["fields"].items():
        print(f"  {labels[k]:28} {v['correct']}/{v['n']}  {pct(v['accuracy'])}")
    cd = agg["clause_detection"]
    print(f"Détection de clauses (booléens) : TP={cd['tp']} FP={cd['fp']} FN={cd['fn']} TN={cd['tn']} "
          f"precision={pct(cd['precision'])} recall={pct(cd['recall'])}")
    print("-" * 72)
    print(f"Liste exacte des erreurs ({len(errors)}) :")
    for e in errors:
        print("  " + e)
    if skipped:
        print("-" * 72)
        print("Ignorés : " + "; ".join(skipped))
    n_out = sum(len(v) for v in unevaluated.values())
    if n_out:
        print(f"Événements v1 hors du schéma des vérités terrain (non comptés, ni TP ni FP) : {n_out}")
    print(f"\nDétail : data/results/evaluation_{stamp}.json")
    if agg["critical_false_negatives"] and not args.no_fail:
        print(f"ÉCHEC : {agg['critical_false_negatives']} faux négatif(s) sur des catégories critiques.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
