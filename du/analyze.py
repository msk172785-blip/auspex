"""Analyse en ligne de commande (sans interface).

Usage :
    python analyze.py CCAP.pdf [AVENANT.pdf ...] [--start 2026-01-15] [--amount 220000] [--coef 1.03] [--ref 2026-10-03]
    python analyze.py data/simulated/case_A          # dossier (meta.json / invoices.json … facultatifs)
Le JSON complet est écrit dans data/results/<nom>_analysis.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from du_engine.calculations import fmt_eur  # noqa: E402
from du_engine.corpus import analyze_case  # noqa: E402
from du_engine.pipeline import analyze_pdfs  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--start", help="date de début / notification (AAAA-MM-JJ)")
    ap.add_argument("--amount", type=float, help="montant annuel HT")
    ap.add_argument("--coef", type=float, help="coefficient de révision")
    ap.add_argument("--ref", help="date de référence (AAAA-MM-JJ), défaut : aujourd'hui")
    args = ap.parse_args(argv)
    ref = date.fromisoformat(args.ref) if args.ref else None
    p0 = Path(args.paths[0])
    if p0.is_dir():
        a = analyze_case(p0, reference_date=ref)
    else:
        user = {"contract_start_date": args.start, "annual_amount": args.amount, "revision_coefficient": args.coef}
        a = analyze_pdfs([Path(p) for p in args.paths], user_inputs=user, reference_date=ref, contract_key=p0.stem)
    out = ROOT / "data" / "results" / f"{a.contract_key}_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(a.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if a.SIMULATED_EXAMPLE:
        print("*** EXEMPLE SIMULÉ — aucune somme réelle n'est réclamée ***")
    for w in a.warnings:
        print("AVERTISSEMENT :", w)
    print(f"{len(a.events)} événement(s) financier(s) :")
    for e in a.events:
        ev = e.evidence[0] if e.evidence else None
        src = f"{ev.document} — art. {ev.article or '?'} — p. {ev.page}" if ev else "données de rapprochement"
        line = f"  [{e.severity.upper()}] {e.title} | {e.status}"
        if e.calculated_deadline:
            line += f" | échéance {date.fromisoformat(e.calculated_deadline).strftime('%d/%m/%Y')}"
        if e.potential_amount:
            line += f" | impact {fmt_eur(e.potential_amount)}"
        print(line + f" | source : {src}")
        if e.missing_information:
            print("      manquant : " + ", ".join(e.missing_information))
    print(f"JSON : {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
