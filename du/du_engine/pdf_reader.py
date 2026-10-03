"""Lecture des PDF page par page + repérage des articles.

Aucune OCR : un PDF scanné (sans couche texte) est signalé, jamais "deviné".
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentText, PageText

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "’": "'", "‘": "'",
              " ": " ", " ": " ", " ": " ", "–": "-", "—": "-", "‑": "-"}

# "Article 4.3 - ...", "ARTICLE 4 :", "Art. 12.1", "4.3. Révision des prix" (titre numéroté en début de ligne)
_ARTICLE_RE = re.compile(
    r"^\s*(?:article|art\.)\s*(\d+(?:[.\-]\d+)*)\b",
    re.IGNORECASE,
)
_NUMBERED_TITLE_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+([A-ZÉÈÀÂÎÔÛÇ][^\n]{2,80})$")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    # césures de fin de ligne "révi-\nsion" -> "révision"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _article_marks(text: str) -> list[tuple[int, str]]:
    marks = []
    offset = 0
    for line in text.split("\n"):
        m = _ARTICLE_RE.match(line)
        if m:
            marks.append((offset, m.group(1).replace("-", ".")))
        else:
            m2 = _NUMBERED_TITLE_RE.match(line)
            if m2:
                marks.append((offset, m2.group(1)))
        offset += len(line) + 1
    return marks


def classify_document(name: str, first_page_text: str) -> str:
    head = (name + " " + first_page_text[:600]).lower()
    if re.search(r"\bavenant\b", head) and not re.search(r"cahier des clauses", head):
        return "AMENDMENT"
    return "CONTRACT"


def read_pdf(path: str | Path, display_name: str | None = None) -> DocumentText:
    path = Path(path)
    name = display_name or path.name
    warnings: list[str] = []
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # PDF illisible
        return DocumentText(name=name, pages=[], has_text_layer=False,
                            warnings=[f"PDF illisible ({exc.__class__.__name__}: {exc})"])
    pages: list[PageText] = []
    current_article = None
    chars = 0
    for i, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as exc:
            raw = ""
            warnings.append(f"Page {i} : extraction du texte impossible ({exc.__class__.__name__})")
        text = normalize_text(raw)
        chars += len(text)
        marks = _article_marks(text)
        pages.append(PageText(document=name, page=i, text=text, article_marks=marks,
                              article_at_start=current_article))
        if marks:
            current_article = marks[-1][1]
    has_text = chars > 50 * max(1, len(pages)) * 0.2
    if not has_text:
        warnings.append("Aucune couche texte exploitable : PDF probablement scanné. "
                        "L'OCR n'est pas implémentée dans cette version ; aucune donnée n'est extraite.")
    doc = DocumentText(name=name, pages=pages, has_text_layer=has_text, warnings=warnings)
    doc.doc_type = classify_document(name, pages[0].text if pages else "")
    return doc


def article_at(page: PageText, offset: int) -> str | None:
    art = page.article_at_start
    for off, a in page.article_marks:
        if off <= offset:
            art = a
        else:
            break
    return art
