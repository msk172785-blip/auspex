"""Entrée « extraction texte » : découpe un texte en pages d'après les pieds de page « Page N sur M ».

Utilisé lorsque le PDF original n'est pas accessible mais que son texte l'est. Le reste du pipeline
(normalisation, segmentation, extraction, vérification) est identique à l'entrée PDF.
"""
from __future__ import annotations

import re

from .models import DocumentText, PageText
from .pdf_reader import _article_marks, classify_document, normalize_text

FOOTER = re.compile(r"^\s*Page\s+(\d+)\s+(?:sur|/)\s+(\d+)\s*$", re.MULTILINE)


def text_to_document(raw: str, name: str, warning: str = "Entrée = extraction texte (PDF original non utilisé).") -> DocumentText:
    pages, start, current = [], 0, None
    for m in FOOTER.finditer(raw):
        text = normalize_text(raw[start:m.end()])
        marks = _article_marks(text)
        pages.append(PageText(document=name, page=int(m.group(1)), text=text, article_marks=marks, article_at_start=current))
        if marks:
            current = marks[-1][1]
        start = m.end()
    tail = raw[start:].strip()
    if tail or not pages:
        text = normalize_text(raw[start:])
        pages.append(PageText(document=name, page=(pages[-1].page + 1 if pages else 1), text=text, article_marks=_article_marks(text)))
    doc = DocumentText(name=name, pages=pages, has_text_layer=True, warnings=[warning])
    doc.doc_type = classify_document(name, pages[0].text if pages else "")
    return doc
