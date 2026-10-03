"""Point d'entrée : PDF (+ saisies facultatives + données de rapprochement) -> ContractAnalysis."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from .events import build_events
from .extractor import extract_fields
from .models import (MISSING, REVIEW_REQUIRED, USER_INPUT, ContractAnalysis, DocumentText,
                     ExtractedField)
from .pdf_reader import read_pdf

USER_FIELDS = ["contract_title", "buyer", "supplier", "annual_amount", "contract_start_date"]


def _apply_user_inputs(fields: dict[str, ExtractedField], user: dict) -> None:
    """Une saisie utilisateur remplace la valeur affichée mais la valeur extraite reste tracée.
    En cas de divergence, le champ passe en REVIEW_REQUIRED."""
    for k in USER_FIELDS:
        v = user.get(k)
        if v in (None, ""):
            continue
        old = fields.get(k)
        notes = ["Valeur saisie par l'utilisateur (non vérifiée dans les documents)."]
        status = USER_INPUT
        if old is not None and old.found:
            same = str(old.value).strip().lower() == str(v).strip().lower()
            if k == "annual_amount":
                try:
                    same = abs(float(old.value) - float(v)) < 0.01
                except (TypeError, ValueError):
                    same = False
            if not same:
                notes.append(f"DIVERGENCE avec la valeur extraite du document : {old.value!r}.")
                status = REVIEW_REQUIRED
            else:
                notes.append("Cohérente avec la valeur extraite du document.")
        fields[k] = ExtractedField(name=k, value=v, kind=USER_INPUT,
                                   evidence=old.evidence if old else [], confidence=1.0 if status == USER_INPUT else 0.5,
                                   status=status, notes=notes + (old.notes if old else []))


def analyze_documents(docs: list[DocumentText], user_inputs: Optional[dict] = None, recon: Optional[dict] = None,
                      reference_date: Optional[date] = None, simulated: bool = False,
                      contract_key: str = "contract") -> ContractAnalysis:
    user = {k: v for k, v in (user_inputs or {}).items() if v not in (None, "")}
    recon = recon or {}
    ref = reference_date or date.today()
    warnings: list[str] = []
    for d in docs:
        warnings += [f"{d.name} : {w}" for w in d.warnings]
    if not any(d.has_text_layer and d.doc_type == "CONTRACT" for d in docs):
        warnings.append("Aucun document contractuel exploitable (CCAP/AE/CCP) : aucune clause ne peut être extraite.")
    if not simulated and any("EXEMPLE SIMULÉ" in pg.text.upper() for d in docs for pg in d.pages[:2]):
        simulated = True
        warnings.append("Document marqué « EXEMPLE SIMULÉ » : analyse traitée comme une simulation.")
    fields, amendments = extract_fields(docs)
    _apply_user_inputs(fields, user)
    events, fields = build_events(fields, amendments, user, recon, ref, simulated)
    if fields.get("contract_end_date") is None:
        fields["contract_end_date"] = ExtractedField("contract_end_date", kind=MISSING)
    return ContractAnalysis(contract_key=contract_key, documents=[d.name for d in docs], fields=fields, events=events,
                            user_inputs=user, warnings=warnings, reference_date=ref.isoformat(),
                            SIMULATED_EXAMPLE=simulated)


def analyze_pdfs(paths: list[str | Path], **kw) -> ContractAnalysis:
    docs = [read_pdf(p) for p in paths]
    return analyze_documents(docs, **kw)
