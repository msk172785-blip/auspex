"""Vérification stricte d'une interprétation contre le texte source.

Règles (toutes déterministes) :
 1. Chaque extrait doit être retrouvé dans le document : EXACT (dans la page annoncée),
    EXACT_OTHER_PAGE (page corrigée), FUZZY (≥ 0,95 de similarité, texte réellement trouvé stocké),
    sinon NOT_FOUND.
 2. Page et article sont RECALCULÉS à partir de la position retrouvée (jamais repris de l'interpréteur).
 3. Chaque nombre de la valeur (montants, pourcentages, délais) doit apparaître dans un extrait ou dans
    la même clause (section) — chiffres ou lettres.
 4. Échec de 1 ou 3 => REJECTED_UNSUPPORTED. FUZZY / page corrigée => REVIEW_REQUIRED au mieux.
"""
from __future__ import annotations

import difflib
import re
from typing import Optional

from . import lexicon as L
from .document import StructuredDocument, squash
from .schema import AUTO_EXTRACTED, REJECTED_UNSUPPORTED, REVIEW_REQUIRED, Clause

_NORM_MAP = str.maketrans({"’": "'", "‘": "'", "«": '"', "»": '"', "–": "-", "—": "-", "−": "-", " ": " ", " ": " "})


def norm(s: str) -> str:
    return squash(s.translate(_NORM_MAP)).lower()


class Verifier:
    FUZZY_MIN = 0.95

    def __init__(self, sd: StructuredDocument):
        self.sd = sd
        self.clean_norm, self._map = self._build_norm_index(sd.clean_text)
        self.pages_norm = {p: norm(t) for p, t in sd.pages_raw.items()}

    @staticmethod
    def _build_norm_index(text: str) -> tuple[str, list[int]]:
        """Texte normalisé + table de correspondance index_normalisé -> offset original."""
        t = text.translate(_NORM_MAP)
        out, mapping, prev_space = [], [], False
        for i, ch in enumerate(t):
            if ch.isspace():
                if prev_space or not out:
                    continue
                out.append(" ")
                mapping.append(i)
                prev_space = True
            else:
                out.append(ch.lower())
                mapping.append(i)
                prev_space = False
        return "".join(out), mapping

    def locate(self, quote: str) -> tuple[str, Optional[int], Optional[int], Optional[str]]:
        """-> (match, offset_debut, offset_fin, texte_trouvé) dans clean_text."""
        q = norm(quote.replace("[…]", "").replace("...", ""))
        if len(q) < 12:
            return "NOT_FOUND", None, None, None
        i = self.clean_norm.find(q)
        if i >= 0:
            a, z = self._map[i], self._map[i + len(q) - 1] + 1
            return "EXACT", a, z, self.sd.clean_text[a:z]
        # approché : on cherche la meilleure fenêtre autour d'un ancrage (début de l'extrait)
        head = q[:30]
        best = (0.0, None)
        starts = [m.start() for m in re.finditer(re.escape(head[:15]), self.clean_norm)] or []
        if not starts:
            sm = difflib.SequenceMatcher(None, self.clean_norm, q, autojunk=False)
            blk = max(sm.get_matching_blocks(), key=lambda b: b.size)
            if blk.size >= 20:
                starts = [max(0, blk.a - blk.b)]
        for st in starts[:50]:
            cand = self.clean_norm[st:st + len(q) + 20]
            r = difflib.SequenceMatcher(None, cand[:len(q)], q, autojunk=False).ratio()
            if r > best[0]:
                best = (r, st)
        if best[1] is not None and best[0] >= self.FUZZY_MIN:
            st = best[1]
            a, z = self._map[st], self._map[min(st + len(q) - 1, len(self._map) - 1)] + 1
            return "FUZZY", a, z, self.sd.clean_text[a:z]
        return "NOT_FOUND", None, None, None

    def _numbers_grounded(self, clause: Clause, support_text: str) -> list[str]:
        """Ancrage TYPÉ : un pourcentage doit apparaître comme « N % », un montant comme une somme en euros,
        un délai comme « N unité ». Un chiffre isolé (numéro d'article, date…) ne suffit pas.
        Retourne la liste des valeurs NON ancrées."""
        txt = squash(support_text.translate(_NORM_MAP))
        pcts = {round(float(m.group(1).replace(",", ".")), 4) for m in L.PCT_RE.finditer(txt)}
        money = {round(L.parse_money(m.group(1)), 2) for m in L.MONEY_RE.finditer(txt)}
        durations = {(L.to_int(m.group(1)), L.unit_norm(m.group(2))) for m in L.DURATION_RE.finditer(txt)}
        missing = []
        for a in clause.amounts:
            if round(float(a.value), 2) not in money:
                missing.append(f"montant {a.value}")
        for p in clause.percentages:
            if round(float(p.value), 4) not in pcts:
                missing.append(f"pourcentage {p.value}")
        dl = clause.deadline_rule or {}
        if dl.get("amount") is not None and dl.get("unit") not in (None, "none", "fixed_day"):
            if (dl["amount"], dl["unit"]) not in durations:
                missing.append(f"délai {dl['amount']} {dl['unit']}")
        cn = (clause.consequence_if_no_action or {}).get("duration")
        if cn and cn.get("amount") is not None and (cn["amount"], cn.get("unit")) not in durations:
            missing.append(f"durée {cn['amount']} {cn.get('unit')}")
        return missing

    def verify(self, clause: Clause) -> Clause:
        if not clause.evidence:
            clause.status = REJECTED_UNSUPPORTED
            clause.checks.append("FAIL: aucune citation fournie")
            return clause
        support = []
        all_ok, degraded = True, False
        first_pos = None
        for ev in clause.evidence:
            match, a, z, found = self.locate(ev.quote)
            ev.match, ev.found_text = match, found
            if match == "NOT_FOUND":
                all_ok = False
                clause.checks.append(f"FAIL: citation introuvable : « {ev.quote[:80]}… »")
                continue
            page, page_end = self.sd.page_of(a), self.sd.page_of(z - 1)
            sec = self.sd.section_at(a)
            claimed_page = ev.page
            if claimed_page is not None and claimed_page != page:
                degraded = True
                clause.checks.append(f"WARN: page corrigée {claimed_page} -> {page}")
                ev.match = "EXACT_OTHER_PAGE" if match == "EXACT" else match
            if ev.article and sec and sec.number and ev.article != sec.number:
                clause.checks.append(f"WARN: article corrigé {ev.article} -> {sec.number}")
                degraded = True
            ev.page, ev.page_end = page, page_end
            ev.start, ev.end = a, z
            ev.article = sec.number if sec else None
            if match == "FUZZY":
                degraded = True
                clause.checks.append("WARN: correspondance approchée (texte retrouvé stocké)")
            if first_pos is None:
                first_pos = a
                clause.source_page, clause.source_article = page, ev.article
                clause.section_id = sec.sid if sec else clause.section_id
            support.append(found or "")
            if sec:
                body = self.sd.clean_text[sec.start:sec.end]
                if sec.sid != "S0":  # la ligne de titre (numéro d'article) n'ancre aucune valeur
                    body = body.split("\n", 1)[1] if "\n" in body else ""
                support.append(body)
        if not all_ok:
            clause.status = REJECTED_UNSUPPORTED
            return clause
        clause.checks.append("OK: toutes les citations retrouvées dans la source")
        if clause.source_article is not None and clause.source_article not in self.sd.article_numbers():
            clause.status = REJECTED_UNSUPPORTED
            clause.checks.append("FAIL: article inexistant")
            return clause
        unanchored = self._numbers_grounded(clause, " ".join(support))
        if unanchored:
            clause.status = REJECTED_UNSUPPORTED
            clause.checks.append("FAIL: nombres non présents dans la clause : " + ", ".join(unanchored))
            return clause
        clause.checks.append("OK: nombres ancrés dans la clause")
        if degraded or clause.review_reasons or clause.missing_information or clause.confidence < 0.8:
            clause.status = REVIEW_REQUIRED
        else:
            clause.status = AUTO_EXTRACTED
        return clause
