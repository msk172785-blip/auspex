"""Structures de données de DÛ.

Trois natures de données sont strictement séparées (champ `kind`) :
  FACT        — information présente littéralement dans un document (preuve obligatoire)
  CALCULATION — résultat d'un calcul déterministe Python (étapes obligatoires)
  USER_INPUT  — information saisie par l'utilisateur (non vérifiée par DÛ)
  MISSING     — information introuvable : jamais devinée

Statuts possibles produits par le moteur :
  AUTO_EXTRACTED  — extraction automatique, preuve littérale vérifiée, confiance >= seuil
  REVIEW_REQUIRED — incertitude, conflit ou information manquante
  NOT_FOUND       — aucune mention trouvée (ce n'est PAS une preuve d'absence)
Le statut VALIDATED n'est jamais produit par le moteur : il est réservé à une
validation humaine explicite (interface ou vérité terrain).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

FACT = "FACT"
CALCULATION = "CALCULATION"
USER_INPUT = "USER_INPUT"
MISSING = "MISSING"

AUTO_EXTRACTED = "AUTO_EXTRACTED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
NOT_FOUND = "NOT_FOUND"
VALIDATED = "VALIDATED"  # humain uniquement

AUTO_CONFIDENCE_THRESHOLD = 0.80

EVENT_TYPES = [
    "PRICE_REVISION",
    "PRICE_REVISION_DEADLINE",
    "PRICE_REVISION_FORFEITURE",
    "PRICE_REVISION_THRESHOLD",
    "AMENDMENT_PRICE_CHANGE",
    "PURCHASE_ORDER_BILLING",
    "VARIABLE_SERVICE_BILLING",
    "RETENTION_RELEASE",
    "FINAL_BALANCE",
    "OTHER_FINANCIAL_RIGHT",
]

# Événements dont l'oubli fait perdre de l'argent à date fixe : un faux négatif
# sur ces types est classé "critique" dans l'évaluation.
DEADLINE_EVENT_TYPES = {
    "PRICE_REVISION_DEADLINE",
    "PRICE_REVISION_FORFEITURE",
    "RETENTION_RELEASE",
    "FINAL_BALANCE",
}


@dataclass
class Evidence:
    document: str
    page: int  # 1-indexé
    article: Optional[str]
    quote: str
    quote_verified: bool = False  # l'extrait existe-t-il littéralement dans le texte de la page ?

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractedField:
    name: str
    value: Any = None
    kind: str = MISSING
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    status: str = NOT_FOUND
    missing_information: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.kind != MISSING and self.value is not None

    @property
    def first_evidence(self) -> Optional[Evidence]:
        return self.evidence[0] if self.evidence else None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class FinancialEvent:
    financial_event_type: str
    severity: str  # critical | high | medium | info
    title: str
    contractual_fact: dict
    financial_calculation: Optional[dict]
    evidence: list[Evidence]
    confidence: float
    status: str
    action: str = ""
    missing_information: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    calculated_deadline: Optional[str] = None  # ISO
    potential_amount: Optional[float] = None
    SIMULATED_EXAMPLE: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class PageText:
    document: str
    page: int
    text: str
    # article actif au début de la page et repères (offset -> article)
    article_marks: list[tuple[int, str]] = field(default_factory=list)
    article_at_start: Optional[str] = None


@dataclass
class DocumentText:
    name: str
    pages: list[PageText]
    has_text_layer: bool
    warnings: list[str] = field(default_factory=list)
    doc_type: str = "CONTRACT"  # CONTRACT | AMENDMENT


@dataclass
class ContractAnalysis:
    contract_key: str
    documents: list[str]
    fields: dict[str, ExtractedField]
    events: list[FinancialEvent]
    user_inputs: dict
    warnings: list[str]
    reference_date: str
    SIMULATED_EXAMPLE: bool = False
    engine_version: str = "0.1.0"

    def to_dict(self) -> dict:
        return {
            "contract_key": self.contract_key,
            "documents": self.documents,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "events": [e.to_dict() for e in self.events],
            "user_inputs": self.user_inputs,
            "warnings": self.warnings,
            "reference_date": self.reference_date,
            "SIMULATED_EXAMPLE": self.SIMULATED_EXAMPLE,
            "engine_version": self.engine_version,
        }
