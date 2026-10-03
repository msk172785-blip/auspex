"""Schéma sémantique v1 des clauses financières.

Une `Clause` est une INTERPRÉTATION (frames locaux ou LLM). Elle ne devient utilisable qu'après
vérification (verify.py) : preuve retrouvée dans le texte, nombres ancrés, article et page valides.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# statuts
AUTO_EXTRACTED = "AUTO_EXTRACTED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
REJECTED_UNSUPPORTED = "REJECTED_UNSUPPORTED"
VALIDATED = "VALIDATED"  # humain uniquement, jamais produit par le moteur

EVENT_TYPES = [
    "PRICE_REVISION",              # existence et mécanique d'un nouveau prix (formule, indice, calendrier)
    "PRICE_REVISION_DEADLINE",     # délai pour demander / déclencher la révision
    "SUPPLIER_ACTION_REQUIRED",    # action que le titulaire doit accomplir pour obtenir/garder un droit
    "CONSEQUENCE_IF_NO_ACTION",    # ce qui se passe si une partie n'agit pas (perte de droit, acceptation tacite…)
    "PRICE_REVISION_THRESHOLD",    # plafond (annuel/cumulé), seuil de déclenchement, clause de sauvegarde
    "AMENDMENT_PRICE_CHANGE",
    "PURCHASE_ORDER_BILLING",
    "VARIABLE_SERVICE_BILLING",
    "BILLING_CONDITION",
    "PAYMENT_TERM",
    "LATE_PAYMENT_INTEREST",
    "ADVANCE_PAYMENT",
    "REEXAMINATION_RIGHT",
    "RETENTION_RELEASE",
    "FINAL_BALANCE",
    "PENALTY_EXPOSURE",
    "OTHER_FINANCIAL_RIGHT",
]

CRITICAL_TYPES = {
    "PRICE_REVISION", "PRICE_REVISION_DEADLINE", "SUPPLIER_ACTION_REQUIRED", "CONSEQUENCE_IF_NO_ACTION",
    "PRICE_REVISION_THRESHOLD", "AMENDMENT_PRICE_CHANGE", "PURCHASE_ORDER_BILLING", "BILLING_CONDITION",
}

AMOUNT_ROLES = [
    "ANNUAL_CONTRACT_VALUE", "PURCHASE_ORDER_ANNUAL_CEILING", "PURCHASE_ORDER_ANNUAL_MINIMUM", "CONTRACT_CEILING",
    "ADVANCE_ELIGIBILITY_THRESHOLD", "PENALTY_RATE", "PENALTY_EXEMPTION_THRESHOLD", "SUBCONTRACT_DIRECT_PAYMENT_THRESHOLD",
    "OLD_UNIT_PRICE", "NEW_UNIT_PRICE", "RETENTION_AMOUNT", "UNIT_PRICE", "FLAT_FEE", "OTHER",
]
PERCENT_ROLES = ["CAP", "THRESHOLD", "FORMULA_WEIGHT", "PENALTY", "OTHER"]
PERCENT_SUBROLES = ["CAP_ANNUAL", "CAP_CUMULATIVE", "TRIGGER_THRESHOLD", "SAFEGUARD", "ADVANCE_RATE", "RETENTION_RATE",
                    "COST_SHARE", "MODIFICATION_CAP", "ADVANCE_REPAYMENT", "OTHER"]
CONSEQUENCE_TYPES = ["PRICE_KEPT", "RIGHT_LOST", "DEEMED_ACCEPTED", "DEEMED_NOT_PERFORMED", "PENALTY", "PRICE_APPLIED", "OTHER"]


@dataclass
class Evidence:
    document: str
    page: Optional[int]
    page_end: Optional[int]
    article: Optional[str]
    quote: str                         # extrait proposé par l'interpréteur
    found_text: Optional[str] = None   # texte réellement retrouvé dans la source
    match: str = "NOT_CHECKED"         # EXACT | EXACT_OTHER_PAGE | FUZZY | NOT_FOUND
    start: Optional[int] = None        # position retrouvée dans le texte nettoyé (posée par verify)
    end: Optional[int] = None


@dataclass
class Amount:
    value: float
    unit: str
    role: str
    raw: str = ""


@dataclass
class Percentage:
    value: float
    role: str
    subrole: str = "OTHER"
    raw: str = ""


@dataclass
class Clause:
    event_type: str
    actor: str = "UNKNOWN"                   # SUPPLIER | BUYER | BOTH | UNKNOWN
    actor_basis: str = ""                    # EXPLICIT | PRONOUN | INFERRED_FROM_SECTION | NONE
    action_required: str = ""
    trigger: str = ""
    deadline_rule: Optional[dict] = None     # {amount, unit, direction, anchor, anchor_text, qualifier}
    deadline_basis: str = ""
    date_expression: Optional[str] = None
    consequence_if_action: str = ""
    consequence_if_no_action: Optional[dict] = None  # {type, polarity_for_supplier, text, inactive_party}
    amounts: list[Amount] = field(default_factory=list)
    percentages: list[Percentage] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    section_id: Optional[str] = None
    source_page: Optional[int] = None
    source_article: Optional[str] = None
    source_quote: str = ""
    interpreter: str = "FRAMES"              # FRAMES | LLM | BASELINE
    confidence: float = 0.0
    status: str = REVIEW_REQUIRED
    checks: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)
    critical: bool = False
    human_review_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# Schéma JSON imposé au LLM (structured outputs). Les champs de preuve sont des citations ;
# page/article sont recalculés par le code à partir du texte, jamais crus sur parole.
LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clauses"],
    "properties": {
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["event_type", "actor", "action_required", "trigger", "deadline_rule", "deadline_basis",
                             "consequence_if_action", "consequence_if_no_action", "amounts", "percentages", "quotes",
                             "uncertainty", "notes"],
                "properties": {
                    "event_type": {"type": "string", "enum": EVENT_TYPES},
                    "actor": {"type": "string", "enum": ["SUPPLIER", "BUYER", "BOTH", "UNKNOWN"]},
                    "action_required": {"type": "string"},
                    "trigger": {"type": "string"},
                    "deadline_rule": {
                        "type": "object", "additionalProperties": False,
                        "required": ["amount", "unit", "direction", "anchor", "anchor_text"],
                        "properties": {
                            "amount": {"type": ["integer", "null"]},
                            "unit": {"type": "string", "enum": ["days", "months", "years", "weeks", "hours", "none"]},
                            "direction": {"type": "string", "enum": ["before", "after", "none"]},
                            "anchor": {"type": "string", "enum": ["ANNIVERSARY", "NOTIFICATION", "RECEIPT", "EXECUTION_START",
                                                                  "TERM_END", "REPORT", "OTHER", "NONE"]},
                            "anchor_text": {"type": "string"},
                        },
                    },
                    "deadline_basis": {"type": "string"},
                    "consequence_if_action": {"type": "string"},
                    "consequence_if_no_action": {
                        "type": "object", "additionalProperties": False,
                        "required": ["type", "polarity_for_supplier", "inactive_party", "text"],
                        "properties": {
                            "type": {"type": "string", "enum": CONSEQUENCE_TYPES + ["NONE"]},
                            "polarity_for_supplier": {"type": "string", "enum": ["FAVORABLE", "UNFAVORABLE", "NEUTRAL", "UNKNOWN"]},
                            "inactive_party": {"type": "string", "enum": ["SUPPLIER", "BUYER", "UNKNOWN", "NONE"]},
                            "text": {"type": "string"},
                        },
                    },
                    "amounts": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["value", "unit", "role"],
                        "properties": {"value": {"type": "number"}, "unit": {"type": "string"},
                                       "role": {"type": "string", "enum": AMOUNT_ROLES}}}},
                    "percentages": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["value", "role", "subrole"],
                        "properties": {"value": {"type": "number"}, "role": {"type": "string", "enum": PERCENT_ROLES},
                                       "subrole": {"type": "string", "enum": PERCENT_SUBROLES}}}},
                    "quotes": {"type": "array", "items": {"type": "string"}},
                    "uncertainty": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                    "notes": {"type": "string"},
                },
            },
        }
    },
}
