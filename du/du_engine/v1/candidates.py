"""Génération LARGE de clauses candidates (objectif : rappel).

Chaque paragraphe reçoit un profil de concepts. Il est candidat dès qu'un concept économique est actif.
Les candidats servent à : (1) choisir ce qui est envoyé à l'interpréteur LLM, (2) prouver quelles zones
ont été examinées, (3) signaler les zones économiques fortes que AUCUNE interprétation vérifiée ne couvre
(« candidat non interprété » => REVIEW_REQUIRED, jamais un silence).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import lexicon as L
from .document import StructuredDocument, squash
from .frames import PRICE_MECHANISM

CONCEPTS = {
    "PRICE": L.PRICE, "CHANGE": L.CHANGE, "INDEX": L.INDEX, "FORMULA": L.FORMULA, "OBLIGATION": L.OBLIGATION,
    "ACTION": L.ACTION_VERB, "REQUEST": L.REQUEST, "INACTION_COND": L.INACTION_COND, "OUT_PRICE_KEPT": L.OUT_PRICE_KEPT,
    "OUT_RIGHT_LOST": L.OUT_RIGHT_LOST, "OUT_DEEMED_ACCEPTED": L.OUT_DEEMED_ACCEPTED, "OUT_DEEMED_NOT_DONE": L.OUT_DEEMED_NOT_DONE,
    "CAP": L.CAP_CUE, "THRESHOLD": L.THRESHOLD_CUE, "PURCHASE_ORDER": L.PURCHASE_ORDER, "VARIABLE": L.VARIABLE_SERVICE,
    "INVOICE": L.INVOICE, "PAYMENT": L.PAYMENT, "CONDITION_ON": L.CONDITION_ON, "ADVANCE": L.ADVANCE, "RETENTION": L.RETENTION,
    "FINAL_BALANCE": L.FINAL_BALANCE, "MECHANISM": PRICE_MECHANISM, "LATE_INTEREST": L.LATE_INTEREST, "PENALTY": L.PENALTY, "REEXAM": L.REEXAM,
    "MONEY": L.MONEY_RE, "SUPPLIER": L.SUPPLIER,
    "STRICT_CONDITION": __import__("re").compile(r"\b(?:conditionn|subordonn|sous\s+r[ée]serve)", __import__("re").I), "PCT": L.PCT_RE, "DURATION": L.DURATION_RE, "DATE": L.DATE_RE,
}
ECONOMIC = {"PRICE", "INDEX", "FORMULA", "MONEY", "PURCHASE_ORDER", "INVOICE", "PAYMENT", "ADVANCE", "RETENTION",
            "FINAL_BALANCE", "LATE_INTEREST", "PENALTY", "REEXAM"}


@dataclass
class Candidate:
    paragraph: int
    section: str
    page: int
    concepts: set[str]
    strong: list[str] = field(default_factory=list)   # motifs composés « forts »
    text: str = ""


def strong_patterns(c: set[str]) -> list[str]:
    out = []
    if ({"PRICE", "CHANGE", "MECHANISM"} <= c) or "FORMULA" in c or ({"INDEX", "PRICE"} <= c):
        out.append("PRICE_CHANGE")
    if "OUT_RIGHT_LOST" in c and "SUPPLIER" in c and c & {"PRICE", "MONEY", "PAYMENT", "INVOICE"}:
        out.append("RIGHT_LIMITATION")
    if "INACTION_COND" in c and c & {"OUT_PRICE_KEPT", "OUT_RIGHT_LOST", "OUT_DEEMED_ACCEPTED", "OUT_DEEMED_NOT_DONE"}:
        out.append("CONSEQUENCE")
    if "OUT_DEEMED_ACCEPTED" in c:
        out.append("TACIT_ACCEPTANCE")
    if {"OBLIGATION", "ACTION", "DURATION"} <= c and c & ECONOMIC:
        out.append("ECONOMIC_OBLIGATION_WITH_DEADLINE")
    if "PCT" in c and c & {"CAP", "THRESHOLD"} and c & {"PRICE", "CHANGE"}:
        out.append("PRICE_LIMIT")
    if {"INVOICE", "CONDITION_ON", "STRICT_CONDITION"} <= c:
        out.append("BILLING_CONDITION")
    return out


def generate(sd: StructuredDocument) -> list[Candidate]:
    out = []
    for p in sd.paragraphs:
        text = squash(sd.clean_text[p.start:p.end])
        title = sd.section(p.section).title
        concepts = {k for k, rx in CONCEPTS.items() if rx.search(text)}
        title_concepts = {k for k, rx in CONCEPTS.items() if rx.search(title)}
        if not (concepts | title_concepts) & ECONOMIC and not (concepts & {"INACTION_COND"} and concepts & {"OUT_DEEMED_ACCEPTED", "OUT_RIGHT_LOST", "OUT_PRICE_KEPT"}):
            continue
        out.append(Candidate(paragraph=p.idx, section=p.section, page=sd.page_of(p.start), concepts=concepts | {f"T:{c}" for c in title_concepts},
                             strong=strong_patterns(concepts | (title_concepts & {"PRICE", "CHANGE"})), text=text[:400]))
    return out
