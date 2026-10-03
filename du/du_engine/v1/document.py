"""Segmentation v1 : pages -> lignes -> (bruit de page retiré) -> sections hiérarchiques -> paragraphes -> phrases.

Toutes les positions sont des offsets dans `clean_text` (texte sans en-têtes/pieds de page répétés),
avec correspondance offset -> page. Le texte brut de chaque page est conservé pour la vérification.
"""
from __future__ import annotations

import bisect
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from ..models import DocumentText

# Titres : « ARTICLE 4 : PRIX », « Article 4.3 - Révision », « 4.3 - Révision des prix », « 4.2.6. – Contenu »,
# « 7.1.2.1 Personnes … ». Le titre doit commencer par une majuscule (évite « 4.3 du présent document »).
_H_ARTICLE = re.compile(r"^(?:ARTICLE|Article|ART\.|Art\.)\s+(\d{1,2}(?:\.\d{1,2}){0,4})\s*\.?\s*(?:[:\-–—.]\s*)?(.*)$")
_H_DOTTED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,4})\s*\.?\s*(?:[-–—:]\s*)?([A-ZÀ-ÖØ-Þ«\"][^\n]{1,140})$")
_H_SINGLE_CAPS = re.compile(r"^(\d{1,2})\s*[-–—.:)]\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’ \-]{3,100})$")
_PAGE_MARK = re.compile(r"^\s*page\s+\d+\s*(?:sur|/)\s*\d+\s*$", re.IGNORECASE)
_EXTERNAL_REF = re.compile(r"\s*(?:du|de\s+l'|de\s+la)\s*(?:C\.?C\.?A\.?G|Code|code|d[ée]cret|arr[êe]t[ée]|r[èe]glement|loi)")


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Line:
    page: int
    text: str
    raw_start: int          # offset dans le texte de la page
    clean_start: int = -1   # offset dans clean_text (-1 si bruit)
    boilerplate: bool = False


@dataclass
class Section:
    sid: str
    number: Optional[str]
    title: str
    level: int
    start: int              # offset clean_text de la ligne de titre
    end: int = -1
    parent: Optional[str] = None
    page_start: int = 0
    page_end: int = 0

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}".strip() if self.number else self.title


@dataclass
class Sentence:
    idx: int
    start: int
    end: int
    text: str
    section: str
    paragraph: int
    page: int
    page_end: int


@dataclass
class Paragraph:
    idx: int
    start: int
    end: int
    section: str
    sentences: list[int] = field(default_factory=list)


@dataclass
class StructuredDocument:
    name: str
    pages_raw: dict[int, str]
    clean_text: str
    page_offsets: list[tuple[int, int]]  # (clean_offset, page) triés
    sections: list[Section]
    paragraphs: list[Paragraph]
    sentences: list[Sentence]
    anomalies: list[str]
    boilerplate_lines: list[str]
    doc_type: str = "CONTRACT"

    # -- utilitaires
    def page_of(self, offset: int) -> int:
        i = bisect.bisect_right([o for o, _ in self.page_offsets], offset) - 1
        return self.page_offsets[max(i, 0)][1]

    def section(self, sid: str) -> Section:
        return self._by_id[sid]

    def section_at(self, offset: int) -> Optional[Section]:
        best = None
        for s in self.sections:
            if s.start <= offset < s.end and (best is None or s.start >= best.start):
                best = s
        return best

    def section_text(self, sid: str) -> str:
        s = self.section(sid)
        return self.clean_text[s.start:s.end]

    def sentences_in(self, sid: str, include_children: bool = False) -> list[Sentence]:
        ids = {sid}
        if include_children:
            ids |= {s.sid for s in self.sections if self._is_descendant(s.sid, sid)}
        return [x for x in self.sentences if x.section in ids]

    def _is_descendant(self, child: str, ancestor: str) -> bool:
        cur = self._by_id[child].parent
        while cur:
            if cur == ancestor:
                return True
            cur = self._by_id[cur].parent
        return False

    def article_numbers(self) -> set[str]:
        return {s.number for s in self.sections if s.number}

    def __post_init__(self):
        self._by_id = {s.sid: s for s in self.sections}


def _norm_line(t: str) -> str:
    return re.sub(r"\d+", "#", squash(t).lower())


def _heading(line: str) -> Optional[tuple[Optional[str], str]]:
    t = line.strip()
    if len(t) > 160:
        return None
    m = _H_ARTICLE.match(t)
    if m:
        return m.group(1), squash(m.group(2)).strip(" :-–—.")
    m = _H_DOTTED.match(t)
    if m and not re.match(r"^\d{1,2}(?:\.\d{1,2})+\s*(?:€|%|euros?|h\b|heures?)", t):
        return m.group(1), squash(m.group(2)).strip(" :-–—.")
    m = _H_SINGLE_CAPS.match(t)
    if m:
        return m.group(1), squash(m.group(2))
    return None


# fin de phrase, sauf abréviations « R. 2191-3 », « L. 2192 », « M. », « art. 4 », « n° »
_SENT_SPLIT = re.compile(r"(?<![\s(][A-Z]\.)(?<![Aa]rt\.)(?<=[.;!?])\s+(?=[A-ZÀ-ÖØ-Þ«(\-–•✓▪➢0-9])")


def build(doc: DocumentText) -> StructuredDocument:
    pages_raw = {p.page: p.text for p in doc.pages}
    lines: list[Line] = []
    for p in doc.pages:
        off = 0
        for ln in p.text.split("\n"):
            lines.append(Line(page=p.page, text=ln, raw_start=off))
            off += len(ln) + 1

    # 1. bruit de page : lignes répétées sur de nombreuses pages + « Page N sur M »
    n_pages = max(1, len(doc.pages))
    pages_by_norm: dict[str, set[int]] = {}
    for ln in lines:
        if ln.text.strip():
            pages_by_norm.setdefault(_norm_line(ln.text), set()).add(ln.page)
    threshold = max(3, int(0.3 * n_pages))
    boiler_norms = {k for k, v in pages_by_norm.items() if len(v) >= threshold and len(k) < 160} if n_pages >= 3 else set()
    for ln in lines:
        if _PAGE_MARK.match(ln.text) or (ln.text.strip() and _norm_line(ln.text) in boiler_norms):
            ln.boilerplate = True

    # 2. texte nettoyé
    parts, page_offsets, cur = [], [], 0
    last_page = None
    for ln in lines:
        if ln.boilerplate:
            continue
        if ln.page != last_page:
            page_offsets.append((cur, ln.page))
            last_page = ln.page
        ln.clean_start = cur
        parts.append(ln.text)
        cur += len(ln.text) + 1
    clean_text = "\n".join(parts)
    if not page_offsets:
        page_offsets = [(0, 1)]

    def page_of(o: int) -> int:
        i = bisect.bisect_right([x for x, _ in page_offsets], o) - 1
        return page_offsets[max(i, 0)][1]

    # 3. sections
    content = [ln for ln in lines if not ln.boilerplate]
    sections: list[Section] = [Section(sid="S0", number=None, title="(préambule)", level=0, start=0, page_start=page_of(0))]
    for ln in content:
        h = _heading(ln.text)
        if h is None:
            continue
        number, title = h
        level = number.count(".") + 1 if number else 1
        sections.append(Section(sid=f"S{len(sections)}", number=number, title=title, level=level,
                                start=ln.clean_start, page_start=ln.page))
    for i, s in enumerate(sections):
        s.end = sections[i + 1].start if i + 1 < len(sections) else len(clean_text)
        s.page_end = page_of(max(s.start, s.end - 1))
        # parent : section précédente dont le numéro est un préfixe strict, sinon niveau inférieur le plus proche
        if s.number:
            for prev in reversed(sections[:i]):
                if prev.number and s.number.startswith(prev.number + "."):
                    s.parent = prev.sid
                    break
            if s.parent is None:
                for prev in reversed(sections[:i]):
                    if prev.number and prev.level < s.level:
                        s.parent = prev.sid
                        break

    # 4. anomalies de numérotation (signalées, jamais corrigées)
    anomalies = []
    counts = Counter(s.number for s in sections if s.number)
    for num, c in counts.items():
        if c > 1:
            where = [f"p.{s.page_start} « {s.title[:40]} »" for s in sections if s.number == num]
            anomalies.append(f"Numéro d'article {num} utilisé {c} fois : " + " ; ".join(where))
    seq = [s for s in sections if s.number]
    key = lambda n: [int(x) for x in n.split(".")]  # noqa: E731
    for a, b in zip(seq, seq[1:]):
        if key(b.number) < key(a.number) and not b.number.startswith(a.number):
            anomalies.append(f"Ordre non monotone : {a.number} (p.{a.page_start}) puis {b.number} (p.{b.page_start})")
    known = {s.number for s in seq}
    for m in re.finditer(r"\barticle\s+(\d{1,2}(?:\.\d{1,2})+)\.?", clean_text, re.IGNORECASE):
        tail = clean_text[m.end():m.end() + 40]
        if _EXTERNAL_REF.match(tail):
            continue
        if m.group(1).rstrip(".") not in known:
            anomalies.append(f"Renvoi vers un article inexistant dans le document : « {squash(m.group(0))} » (p.{page_of(m.start())})")

    # 5. paragraphes (blocs séparés par ligne vide, sans les lignes de titre), fusion à travers les sauts de page
    heading_starts = {s.start for s in sections if s.sid != "S0"}
    blocks: list[list[Line]] = []
    curb: list[Line] = []
    for ln in content:
        if not ln.text.strip() or ln.clean_start in heading_starts:
            if curb:
                blocks.append(curb)
                curb = []
            continue
        curb.append(ln)
    if curb:
        blocks.append(curb)
    merged: list[list[Line]] = []
    for b in blocks:
        if merged:
            prev = merged[-1]
            prev_txt = prev[-1].text.rstrip()
            first = b[0].text.lstrip()
            same_section = _section_for(sections, prev[0].clean_start) == _section_for(sections, b[0].clean_start)
            if same_section and prev_txt and prev_txt[-1] not in ".:;!?" and first[:1].islower():
                prev.extend(b)
                continue
        merged.append(b)

    paragraphs, sentences = [], []
    for b in merged:
        start = b[0].clean_start
        end = b[-1].clean_start + len(b[-1].text)
        sec = _section_for(sections, start)
        par = Paragraph(idx=len(paragraphs), start=start, end=end, section=sec)
        chunk = clean_text[start:end]
        cuts = [0] + [m.end() for m in _SENT_SPLIT.finditer(chunk)] + [len(chunk)]
        # puces et listes : une ligne commençant par un marqueur de liste ouvre une nouvelle phrase
        for m in re.finditer(r"\n(?=\s*(?:[-–•✓▪➢o●]\s|[a-z]\)\s|\d+\)\s))", chunk):
            cuts.append(m.start() + 1)
        cuts = sorted(set(cuts))
        for a, z in zip(cuts, cuts[1:]):
            seg = chunk[a:z]
            if not seg.strip():
                continue
            lead = len(seg) - len(seg.lstrip())
            s_start, s_end = start + a + lead, start + a + len(seg.rstrip())
            sentences.append(Sentence(idx=len(sentences), start=s_start, end=s_end, text=clean_text[s_start:s_end],
                                      section=sec, paragraph=par.idx, page=page_of(s_start), page_end=page_of(s_end - 1)))
            par.sentences.append(sentences[-1].idx)
        paragraphs.append(par)

    return StructuredDocument(name=doc.name, pages_raw=pages_raw, clean_text=clean_text, page_offsets=page_offsets,
                              sections=sections, paragraphs=paragraphs, sentences=sentences, anomalies=anomalies,
                              boilerplate_lines=sorted(boiler_norms), doc_type=doc.doc_type)


def _section_for(sections: list[Section], offset: int) -> str:
    sid = "S0"
    for s in sections:
        if s.start <= offset:
            sid = s.sid
        else:
            break
    return sid
