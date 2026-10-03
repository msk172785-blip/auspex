"""Analyse en ligne de commande (sans interface).

Usage (moteur hybride v1 par défaut ; --engine baseline pour l'ancien moteur regex) :
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
    ap.add_argument("--notification", help="date de notification (AAAA-MM-JJ), si connue")
    ap.add_argument("--engine", choices=["v1", "baseline"], default="v1")
    ap.add_argument("--llm", action="store_true", help="active l'interpréteur Claude (nécessite des identifiants Anthropic)")
    ap.add_argument("--text", action="store_true", help="les fichiers sont des extractions texte (pages « Page N sur M »)")
    args = ap.parse_args(argv)
    ref = date.fromisoformat(args.ref) if args.ref else None
    p0 = Path(args.paths[0])
    if args.engine == "v1":
        return run_v1(args, ref, p0)
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


def run_v1(args, ref, p0) -> int:
    from du_engine.corpus import load_case
    from du_engine.pdf_reader import read_pdf
    from du_engine.text_input import text_to_document
    from du_engine.v1.engine import analyze_v1
    user = {"contract_start_date": args.start, "annual_amount": args.amount, "revision_coefficient": args.coef,
            "notification_date": args.notification}
    recon, simulated, key = {}, False, p0.stem
    if p0.is_dir():
        case = load_case(p0)
        paths, recon, key = case["pdfs"], case["recon"], case["key"]
        user = {**case["meta"].get("user_inputs", {}), **{k: v for k, v in user.items() if v is not None}}
        simulated = bool(case["meta"].get("SIMULATED_EXAMPLE"))
        if ref is None and case["meta"].get("reference_date"):
            ref = date.fromisoformat(case["meta"]["reference_date"])
    else:
        paths = [Path(p) for p in args.paths]
    docs = [text_to_document(Path(p).read_text(encoding="utf-8"), Path(p).name) if args.text else read_pdf(p) for p in paths]
    r = analyze_v1(docs, user_inputs=user, recon=recon, reference_date=ref, use_llm=args.llm, simulated=simulated, contract_key=key)
    out = ROOT / "data" / "results" / f"{key}_v1_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if r["SIMULATED_EXAMPLE"]:
        print("*** EXEMPLE SIMULÉ — aucune somme réelle n'est réclamée ***")
    for w in r["warnings"] + r["document_anomalies"]:
        print("AVERTISSEMENT :", w)
    print(f"{len(r['events'])} événement(s) vérifié(s), {len(r['rejected_unsupported'])} rejeté(s), "
          f"{len(r['uncovered_candidates'])} zone(s) non couverte(s) à revoir :")
    for e in r["events"]:
        cn = (e["consequence_if_no_action"] or {})
        extra = f" | conséquence {cn.get('type')} ({cn.get('polarity_for_supplier')})" if cn else ""
        nd = e["attributes"].get("next_deadline")
        if nd:
            extra += f" | prochaine échéance {date.fromisoformat(nd).strftime('%d/%m/%Y')}{'' if e['attributes'].get('next_deadline_exact') else ' (au plus tôt)'}"
        if e["attributes"].get("potential_amount"):
            extra += f" | impact {fmt_eur(e['attributes']['potential_amount'])}"
        print(f"  [{'CRITIQUE' if e['critical'] else 'info'}] {e['event_type']} | {e['status']} | p.{e['source_page']} art. {e['source_article']}{extra}")
    print(f"JSON : {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
