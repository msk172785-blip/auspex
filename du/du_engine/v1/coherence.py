"""Contrôles de cohérence inter-clauses. Tout conflit => REVIEW_REQUIRED (jamais de correction silencieuse)."""
from __future__ import annotations

import re

from . import lexicon as L
from .schema import AUTO_EXTRACTED, REJECTED_UNSUPPORTED, REVIEW_REQUIRED, Clause


def _flag(c: Clause, reason: str) -> None:
    c.review_reasons.append(reason)
    c.checks.append("COHERENCE: " + reason)
    if c.status == AUTO_EXTRACTED:
        c.status = REVIEW_REQUIRED


def run(clauses: list[Clause]) -> list[str]:
    report = []
    live = [c for c in clauses if c.status != REJECTED_UNSUPPORTED]

    # 1. CAP != THRESHOLD : une même valeur dans une même phrase ne peut pas être les deux
    for c in live:
        roles = {}
        for p in c.percentages:
            roles.setdefault(p.value, set()).add(p.role)
        for v, rs in roles.items():
            if {"CAP", "THRESHOLD"} <= rs:
                _flag(c, f"{v} % qualifié à la fois CAP et THRESHOLD.")
        quote = " ".join(e.quote for e in c.evidence)
        for p in c.percentages:
            if p.role == "THRESHOLD" and p.subrole == "TRIGGER_THRESHOLD" and L.CAP_CUE.search(quote):
                _flag(c, f"{p.value} % : vocabulaire de plafond présent, seuil de déclenchement douteux.")
    report.append("CAP != THRESHOLD vérifié")

    # 2. plafond annuel et cumulé peuvent coexister : on vérifie seulement qu'ils sont distingués
    caps = [p for c in live for p in c.percentages if p.role == "CAP"]
    if len({p.subrole for p in caps}) == 1 and len({p.value for p in caps}) > 1 and caps[0].subrole in ("CAP_ANNUAL", "OTHER"):
        for c in live:
            if any(p.role == "CAP" for p in c.percentages):
                _flag(c, "Plusieurs plafonds de valeurs différentes sans distinction annuel/cumulé.")
    report.append("plafonds annuel / cumulé distingués")

    # 3. un montant BDC ne devient jamais la valeur du marché
    for c in live:
        for a in c.amounts:
            if a.role == "ANNUAL_CONTRACT_VALUE":
                q = " ".join(e.quote for e in c.evidence)
                if re.search(r"bons?\s+de\s+commande|commandes?\b", q, re.IGNORECASE) and re.search(r"maxim|minim", q, re.IGNORECASE):
                    a.role = "OTHER"
                    _flag(c, f"{a.value} € : contexte « commandes / maximum » — rôle valeur du marché refusé.")
    report.append("montant BDC ≠ valeur du marché")

    # 4. fréquence opérationnelle ≠ fréquence de révision
    for c in live:
        if c.event_type == "PRICE_REVISION" and c.attributes.get("revision_frequency"):
            q = " ".join(e.quote for e in c.evidence)
            if not (L.PRICE.search(q) and (L.CHANGE.search(q) or L.INDEX.search(q))):
                c.attributes.pop("revision_frequency")
                _flag(c, "Fréquence trouvée hors d'une phrase sur les prix : ignorée.")
    report.append("fréquence opérationnelle ≠ fréquence de révision")

    # 5. une conséquence d'inaction n'est pas une action automatique favorable
    kept = [c for c in live if c.event_type == "CONSEQUENCE_IF_NO_ACTION" and (c.consequence_if_no_action or {}).get("type") == "PRICE_KEPT"]
    for c in live:
        if c.event_type == "PRICE_REVISION" and c.trigger == "AUTOMATIC":
            q = " ".join(e.quote for e in c.evidence)
            if L.INACTION_COND.search(q) or any(set(e.quote for e in k.evidence) & set(e.quote for e in c.evidence) for k in kept):
                c.trigger = ""
                _flag(c, "« Automatique » issu d'une phrase de conséquence d'inaction : requalifié.")
    for k in kept:
        if k.consequence_if_no_action.get("polarity_for_supplier") != "UNFAVORABLE":
            _flag(k, "Prix maintenus faute d'action : la polarité doit être défavorable au titulaire.")
    report.append("conséquence d'inaction ≠ action automatique favorable")

    # 6. une date à base conditionnelle n'est pas absolue
    for c in live:
        if c.date_expression and ("max(" in c.date_expression or "one_of(" in c.date_expression or "notification_date" in c.date_expression):
            if "notification_date" not in c.missing_information:
                c.missing_information.append("notification_date")
            if c.status == AUTO_EXTRACTED:
                c.status = REVIEW_REQUIRED
                c.checks.append("COHERENCE: date conditionnelle -> non absolue")
    report.append("date conditionnelle non absolue")

    # 7. durée : max calculé vs max énoncé / dernière date énoncée
    for c in live:
        if c.event_type == "CONTRACT_DURATION":
            mx, stated = c.attributes.get("max_months"), c.attributes.get("stated_max_months")
            if stated and mx and mx > stated:
                _flag(c, f"Durée calculée {mx} mois > durée maximale énoncée {stated} mois.")
    report.append("durée calculée vs énoncée")
    return report
