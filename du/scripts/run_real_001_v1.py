"""RÉGRESSION real_001 avec le moteur hybride v1 (contrat de conception connu : pas une mesure de généralisation).

Sorties : data/results/real_001_v1_regression.json et .md
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from du_engine.text_input import text_to_document  # noqa: E402
from du_engine.v1.engine import analyze_v1  # noqa: E402

CASE = ROOT / "data" / "contracts" / "real_001"
OUT = ROOT / "data" / "results"


def fmt_rule(r):
    if not r:
        return ""
    if r.get("anchor") == "FIXED_DAY":
        return r.get("text", "")
    return f"{r.get('amount')} {r.get('unit')} {r.get('direction')} {r.get('anchor')}"


def main() -> int:
    doc = text_to_document((CASE / "CCP_Lot1_Nettoyage_des_locaux_2026.txt").read_text(encoding="utf-8"),
                           "CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf",
                           "Entrée = extraction texte fournie par l'utilisateur (PDF original non accessible).")
    r = analyze_v1([doc], reference_date=date(2026, 10, 3), contract_key="real_001")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "real_001_v1_regression.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    L = ["# real_001 — régression moteur hybride v1", "",
         "Contrat de CONCEPTION (déjà lu, ayant servi au diagnostic). Ce résultat n'est PAS une validation indépendante.",
         "Interpréteur utilisé : cadres sémantiques locaux (FRAMES). Interpréteur LLM : non exécuté (aucune clé d'API dans l'environnement).",
         "Entrée : extraction texte fournie par l'utilisateur, 40 pages ; annexes absentes.", ""]
    L += ["## Événements retenus (preuves vérifiées)", "", "| id | type | statut | revue humaine | acteur (base) | délai | conséquence | nombres | page / art. |", "|---|---|---|---|---|---|---|---|---|"]
    for e in r["events"]:
        cn = e["consequence_if_no_action"] or {}
        nums = ", ".join([f"{a['value']:g} € {a['role']}" for a in e["amounts"]][:3] + [f"{p['value']:g} % {p['subrole'] if p['subrole'] != 'OTHER' else p['role']}" for p in e["percentages"]])
        L.append(f"| {e['id']} | {e['event_type']} | {e['status']} | {'oui' if e['human_review_required'] else 'non'} | {e['actor']} ({e['actor_basis'] or '-'}) | "
                 f"{fmt_rule(e['deadline_rule'])} | {cn.get('type', '')} {cn.get('polarity_for_supplier', '')} | {nums} | p.{e['source_page']} / {e['source_article']} |")
    L += ["", "## Extraits (preuves)", ""]
    for e in r["events"]:
        L.append(f"- {e['id']} {e['event_type']} :")
        for x in e["evidence"][:4]:
            L.append(f"  - p.{x['page']} art. {x['article']} [{x['match']}] « {x['quote'][:220]} »")
    c = r["contract"]
    L += ["", "## Faits du contrat", "",
          f"- Date de début : expression `{c['start_date'].get('expression')}` ; valeur = {c['start_date']['value']} ; au plus tôt = {c['start_date']['earliest']} ; manquant = {c['start_date']['missing']}",
          f"- Durée : initiale {c['duration']['initial_months']} mois ; reconductions {[(x['times'], x['period_months']) for x in c['duration']['renewals']]} ; "
          f"maximum calculé {c['duration']['max_months']} mois ; maximum énoncé {c['duration'].get('stated_max_months')} mois ; "
          f"dernière date énoncée {c['duration'].get('stated_last_date')} ; recalculée {c['duration'].get('computed_last_date_from_earliest_start')}",
          f"- Valeur annuelle du marché : {c['annual_contract_value']} (le maximum des bons de commande n'est pas utilisé)",
          f"- Délai(s) de paiement : {[fmt_rule(x) for x in c['payment_terms']]}"]
    nxt = [e for e in r["events"] if e["event_type"] == "PRICE_REVISION_DEADLINE"]
    if nxt:
        d = nxt[0]["attributes"].get("deadlines", {})
        L += ["", "## Calcul déterministe des échéances de demande de révision", ""] + [f"- {s}" for s in d.get("steps", [])]
    L += ["", "## Checklist des catégories critiques (revue humaine obligatoire)", ""]
    for k, v in r["critical_checklist"].items():
        L.append(f"- {k} : {v['outcome']} {v['events']}")
    L += ["", "## Zones candidates non couvertes (REVIEW_REQUIRED)", ""]
    L += [f"- p.{u['page']} art. {u['article']} {u['patterns']} : « {u['text'][:200]} »" for u in r["uncovered_candidates"]] or ["- aucune"]
    L += ["", "## Rejetées (REJECTED_UNSUPPORTED)", ""] + ([f"- {e['event_type']} : {e['checks'][-1]}" for e in r["rejected_unsupported"]] or ["- aucune"])
    L += ["", "## Anomalies du document (signalées, non corrigées)", ""] + [f"- {a}" for a in r["document_anomalies"]]
    L += ["", "## Contrôles de cohérence exécutés", ""] + [f"- {x}" for x in r["coherence_checks"]]
    L += ["", "## Signal baseline (regex)", ""] + [f"- {b['baseline_field']} = {b['baseline_value']} (p.{b['page']}) : expliqué par v1 = {b['explained_by_v1']}" for b in r["baseline_signals"]]
    (OUT / "real_001_v1_regression.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(r['events'])} événements, {len(r['rejected_unsupported'])} rejetés, {len(r['uncovered_candidates'])} zones non couvertes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
