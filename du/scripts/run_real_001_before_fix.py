"""Exécution du moteur ACTUEL (règles inchangées) sur real_001 — mesure AVANT correction.

Le PDF original n'étant pas accessible depuis l'environnement, l'entrée est l'extraction texte
fournie par l'utilisateur. Seule la lecture diffère de read_pdf() : le texte est découpé en pages
d'après les pieds de page « Page N sur 40 », puis passe par les MÊMES fonctions
(normalize_text, repérage des articles, classification) et le MÊME pipeline d'extraction.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from du_engine.models import DocumentText, PageText  # noqa: E402
from du_engine.pdf_reader import _article_marks, classify_document, normalize_text  # noqa: E402
from du_engine.pipeline import analyze_documents  # noqa: E402

CASE = ROOT / "data" / "contracts" / "real_001"
TXT = CASE / "CCP_Lot1_Nettoyage_des_locaux_2026.txt"
DOC_NAME = "CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf"
OUT = ROOT / "data" / "results" / "real_001_before_fix.json"
REFERENCE_DATE = date(2026, 10, 3)

FOOTER = re.compile(r"^\s*Page\s+(\d+)\s+sur\s+(\d+)\s*$", re.MULTILINE)


def text_to_document(raw: str, name: str) -> DocumentText:
    pages, start, current = [], 0, None
    for m in FOOTER.finditer(raw):
        n = int(m.group(1))
        text = normalize_text(raw[start:m.end()])
        marks = _article_marks(text)
        pages.append(PageText(document=name, page=n, text=text, article_marks=marks, article_at_start=current))
        if marks:
            current = marks[-1][1]
        start = m.end()
    doc = DocumentText(name=name, pages=pages, has_text_layer=True,
                       warnings=["Entrée = extraction texte fournie par l'utilisateur (PDF original non accessible)."])
    doc.doc_type = classify_document(name, pages[0].text if pages else "")
    return doc


def main() -> int:
    doc = text_to_document(TXT.read_text(encoding="utf-8"), DOC_NAME)
    a = analyze_documents([doc], user_inputs={}, recon={}, reference_date=REFERENCE_DATE,
                          simulated=False, contract_key="real_001")
    assert a.SIMULATED_EXAMPLE is False
    out = a.to_dict()
    out["_run"] = {"engine_rules_modified": False, "input": "TEXT_EXTRACTION", "pages_detected": len(doc.pages),
                   "reference_date": REFERENCE_DATE.isoformat(), "user_inputs": {}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"pages={len(doc.pages)} events={len(a.events)} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
