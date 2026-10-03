"""Extraction des clauses financières par règles explicites (regex sur le français juridique).

Principes :
- Une valeur n'est retenue que si une phrase du document la contient ; la phrase est
  stockée comme preuve (document, page, article, extrait) et sa présence littérale dans
  le texte de la page est re-vérifiée (`quote_verified`).
- Absence de correspondance => NOT_FOUND (jamais "False" par défaut).
- Correspondances contradictoires => REVIEW_REQUIRED.
- Aucun modèle de langage n'intervient dans cette version.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from .models import (AUTO_CONFIDENCE_THRESHOLD, AUTO_EXTRACTED, FACT, MISSING, NOT_FOUND,
                     REVIEW_REQUIRED, DocumentText, Evidence, ExtractedField, PageText)
from .pdf_reader import article_at

# --------------------------------------------------------------------------- utilitaires texte

NUM_WORDS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "quinze": 15, "vingt": 20, "trente": 30,
    "quarante-cinq": 45, "quarante cinq": 45, "soixante": 60, "quatre-vingt-dix": 90, "quatre vingt dix": 90,
}
NUM = (r"(?P<num>\d+|quarante[- ]cinq|quatre[- ]vingt[- ]dix|un|une|deux|trois|quatre|cinq|six|sept|huit|"
       r"neuf|dix|onze|douze|quinze|vingt|trente|soixante)(?:\s*\(\s*\d+\s*\))?")
MONTHS_FR = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
             "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
DATE_RE = re.compile(
    r"\b(?P<d>\d{1,2})(?:er)?\s*(?:/|\s)\s*(?P<m>\d{1,2}|" + "|".join(MONTHS_FR) + r")\s*(?:/|\s)\s*(?P<y>\d{4})\b",
    re.IGNORECASE)
MONEY_RE = re.compile(r"(?P<amt>\d{1,3}(?:[ . ]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|euros?\b)"
                      r"\s*(?P<tax>HT|H\.T\.?|TTC|T\.T\.C\.?)?", re.IGNORECASE)
PCT_RE = re.compile(r"(?P<pct>\d+(?:[,.]\d+)?)\s*(?:%|pour\s*cent)", re.IGNORECASE)

SUPPLIER = r"(?:le\s+)?(?:titulaire|prestataire|fournisseur|cocontractant|candidat retenu)"


def to_int(word: str) -> Optional[int]:
    w = word.lower().strip()
    if w.isdigit():
        return int(w)
    return NUM_WORDS.get(w.replace("-", " ")) or NUM_WORDS.get(w)


def parse_money(s: str) -> Optional[float]:
    s = re.sub(r"[ . ]", "", s).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date_fr(m: re.Match) -> Optional[date]:
    try:
        mo = m.group("m").lower()
        month = int(mo) if mo.isdigit() else MONTHS_FR[mo]
        return date(int(m.group("y")), month, int(m.group("d")))
    except (ValueError, KeyError):
        return None


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------- segmentation

@dataclass
class Sentence:
    doc: str
    page: int
    start: int
    end: int
    text: str
    article: Optional[str]
    page_obj: PageText
    idx: int = 0  # index global dans le document

    def evidence(self, max_len: int = 500) -> Evidence:
        q = squash(self.text)
        if len(q) > max_len:
            q = q[:max_len].rsplit(" ", 1)[0] + " […]"
        verified = verify_quote(q.replace(" […]", ""), self.page_obj.text)
        return Evidence(document=self.doc, page=self.page, article=self.article, quote=q, quote_verified=verified)


def verify_quote(quote: str, page_text: str) -> bool:
    """Contrôle anti-invention : l'extrait doit exister littéralement (espaces normalisés)."""
    return squash(quote) in squash(page_text)


_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÉÈÀÂÎÔÛÇ«(\-•–0-9])|\n(?=\s*(?:[-•–]|\d+[.)]\s|article\b|art\.))",
                       re.IGNORECASE)


def split_sentences(doc: DocumentText) -> list[Sentence]:
    out: list[Sentence] = []
    for page in doc.pages:
        text = page.text
        if not text:
            continue
        cuts = sorted({0, len(text)} | {m.end() for m in _SPLIT_RE.finditer(text)}
                      | {off for off, _ in page.article_marks}
                      | {text.find("\n", off) + 1 for off, _ in page.article_marks if text.find("\n", off) > 0})
        for a, b in zip(cuts, cuts[1:]):
            chunk = text[a:b]
            if not chunk.strip():
                continue
            lead = len(chunk) - len(chunk.lstrip())
            out.append(Sentence(doc=doc.name, page=page.page, start=a + lead, end=b,
                                text=chunk.strip(), article=article_at(page, a + lead), page_obj=page))
    for i, s in enumerate(out):
        s.idx = i
    return out


# --------------------------------------------------------------------------- construction des champs

def make_field(name: str, value, sentences: Iterable[Sentence], confidence: float,
               notes: Optional[list[str]] = None, missing: Optional[list[str]] = None) -> ExtractedField:
    ev = [s.evidence() for s in sentences]
    status = AUTO_EXTRACTED
    if confidence < AUTO_CONFIDENCE_THRESHOLD or not ev or not all(e.quote_verified for e in ev) or missing:
        status = REVIEW_REQUIRED
    return ExtractedField(name=name, value=value, kind=FACT, evidence=ev, confidence=round(confidence, 2),
                          status=status, notes=notes or [], missing_information=missing or [])


def not_found(name: str, note: str = "") -> ExtractedField:
    return ExtractedField(name=name, value=None, kind=MISSING, status=NOT_FOUND, confidence=0.0,
                          notes=[note] if note else ["Aucune mention trouvée (absence de preuve ≠ preuve d'absence)."])


def review_missing(name: str, missing: list[str], notes: list[str], sentences: Iterable[Sentence] = ()) -> ExtractedField:
    return ExtractedField(name=name, value=None, kind=MISSING, status=REVIEW_REQUIRED,
                          evidence=[s.evidence() for s in sentences], confidence=0.0,
                          missing_information=missing, notes=notes)


def find(sentences: list[Sentence], pattern: str | re.Pattern, flags=re.IGNORECASE) -> list[tuple[Sentence, re.Match]]:
    rx = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    res = []
    for s in sentences:
        flat = s.text.replace("\n", " ")
        m = rx.search(flat)
        if m:
            res.append((s, m))
    return res


# --------------------------------------------------------------------------- zone "révision"

REV_KW = re.compile(r"r[ée]vis|variation des prix|\bI\s*0\b|\bI0\b|\bIo\b|\bindices?\b|formule|coefficient", re.IGNORECASE)
REV_STRONG = re.compile(r"r[ée]vis(?:ion|able|é)", re.IGNORECASE)


def revision_zone(sentences: list[Sentence]) -> list[Sentence]:
    """Phrases portant sur la révision : mot-clé dans la phrase, ou jusqu'à 6 phrases
    après une mention de "révision" dans le même article."""
    zone, last_rev_idx, last_rev_art = [], None, None
    for s in sentences:
        flat = s.text.replace("\n", " ")
        if REV_STRONG.search(flat):
            last_rev_idx, last_rev_art = s.idx, (s.doc, s.article)
        if REV_KW.search(flat):
            zone.append(s)
        elif last_rev_idx is not None and s.idx - last_rev_idx <= 6 and (s.doc, s.article) == last_rev_art:
            zone.append(s)
    return zone


# --------------------------------------------------------------------------- extracteurs par champ

def _first_line_value(docs: list[DocumentText], label_rx: str) -> Optional[tuple[str, Sentence]]:
    rx = re.compile(r"^\s*(?:" + label_rx + r")\s*(?:\(s\))?\s*:\s*(?P<v>.+)$", re.IGNORECASE | re.MULTILINE)
    for doc in docs:
        for page in doc.pages[:3]:
            m = rx.search(page.text)
            if m:
                v = m.group("v").strip(" .:-_")
                if len(v) < 3 or re.fullmatch(r"[._\s…-]+", v):
                    continue
                s = Sentence(doc=doc.name, page=page.page, start=m.start(), end=m.end(), text=m.group(0).strip(),
                             article=article_at(page, m.start()), page_obj=page)
                return v, s
    return None


def extract_identity(docs, sentences) -> dict[str, ExtractedField]:
    f: dict[str, ExtractedField] = {}
    r = _first_line_value(docs, r"pouvoir adjudicateur|acheteur(?: public)?|entit[ée] adjudicatrice|"
                                r"ma[iî]tre d'ouvrage|personne publique(?: contractante)?|organisme acheteur")
    f["buyer"] = make_field("buyer", r[0], [r[1]], 0.75) if r else not_found("buyer")
    r = _first_line_value(docs, r"titulaire|raison sociale du titulaire|prestataire retenu")
    f["supplier"] = make_field("supplier", r[0], [r[1]], 0.7) if r else not_found(
        "supplier", "Le titulaire n'est généralement pas nommé dans le CCAP : à saisir.")
    r = _first_line_value(docs, r"objet(?: du march[ée]| de l'accord-cadre| de la consultation| du contrat)?")
    if r:
        f["contract_title"] = make_field("contract_title", r[0], [r[1]], 0.8)
    else:
        hits = find(sentences, r"(?:pr[ée]sent (?:march[ée]|accord-cadre|contrat)|la consultation) a pour objet\s+(?P<v>[^.;]{5,200})")
        f["contract_title"] = (make_field("contract_title", squash(hits[0][1].group("v")), [hits[0][0]], 0.8)
                               if hits else not_found("contract_title"))
    hits = find(sentences, r"(?:march[ée]|accord-cadre|consultation|contrat)\s*(?:public\s*)?n°\s*:?\s*(?P<v>[A-Z0-9][\w\-/.]{1,30})")
    f["contract_id"] = (make_field("contract_id", hits[0][1].group("v").rstrip("."), [hits[0][0]], 0.85)
                        if hits else not_found("contract_id"))
    return f


def extract_amount_duration(sentences) -> dict[str, ExtractedField]:
    f: dict[str, ExtractedField] = {}
    hits = find(sentences, r"montant\s+(?:global\s+)?annuel[^.;]{0,80}?" + MONEY_RE.pattern)
    if hits:
        s, m = hits[0]
        vals = {parse_money(h[1].group("amt")) for h in hits}
        conf = 0.85 if len(vals) == 1 else 0.5
        f["annual_amount"] = make_field("annual_amount", parse_money(m.group("amt")), [s], conf,
                                        notes=[f"Montant {m.group('tax') or 'HT/TTC non précisé'}"] +
                                              (["Plusieurs montants annuels différents trouvés."] if len(vals) > 1 else []))
    else:
        mm = find(sentences, r"montant\s+(?P<k>minimum|maximum)[^.;]{0,80}?" + MONEY_RE.pattern)
        note = "Aucun montant annuel explicite."
        if mm:
            note += " Montants min/max trouvés : " + "; ".join(squash(x[0].text)[:160] for x in mm[:2])
        f["annual_amount"] = review_missing("annual_amount", ["montant annuel (saisie utilisateur)"], [note],
                                            [x[0] for x in mm[:2]])

    hits = find(sentences, r"(?:conclu|pass[ée]|d'une dur[ée]e|pour une (?:dur[ée]e|p[ée]riode)|dur[ée]e (?:du march[ée]|de l'accord-cadre|initiale)[^.;]{0,40}?)"
                           r"[^.;]{0,40}?\b" + NUM + r"\s*(?P<unit>ans?|ann[ée]es?|mois)\b")
    if hits:
        s, m = hits[0]
        n = to_int(m.group("num"))
        months = n * 12 if m.group("unit").lower().startswith("an") else n
        val = {"initial_months": months}
        rec = find([s] + sentences, r"reconductible[^.;]{0,40}?\b" + NUM + r"\s*fois")
        ev = [s]
        if rec:
            k = to_int(rec[0][1].group("num"))
            val["renewals"] = k
            val["max_months"] = months * (1 + k) if k is not None else None
            if rec[0][0] is not s:
                ev.append(rec[0][0])
        f["contract_duration"] = make_field("contract_duration", val, ev, 0.8)
    else:
        f["contract_duration"] = not_found("contract_duration")

    # date de début : date explicite, sinon règle ("à compter de la notification") -> manquante
    hits = find(sentences, r"(?:prend effet|d[ée]bute|commence|ex[ée]cution|dur[ée]e)[^.;]{0,60}?(?:à compter du|à partir du|le)\s+" + DATE_RE.pattern)
    if hits:
        s, m = hits[0]
        d = parse_date_fr(m)
        f["contract_start_date"] = make_field("contract_start_date", d.isoformat() if d else None, [s], 0.8 if d else 0.4)
    else:
        rule = find(sentences, r"(?:à compter|à partir)\s+de\s+(?:la\s+|sa\s+)?(?:date\s+de\s+)?(?:la\s+|sa\s+)?notification")
        if rule:
            f["contract_start_date"] = review_missing(
                "contract_start_date", ["date_notification"],
                ["Le contrat court à compter de sa notification ; la date de notification n'est pas dans le document."],
                [rule[0][0]])
        else:
            f["contract_start_date"] = not_found("contract_start_date")
    f["contract_end_date"] = not_found("contract_end_date", "Calculée uniquement si début et durée sont connus.")
    return f


def extract_price_and_revision(sentences) -> dict[str, ExtractedField]:
    f: dict[str, ExtractedField] = {}
    zone = revision_zone(sentences)

    # --- type de prix
    firm = find(sentences, r"prix\s+(?:sont|est|seront|du march[ée] sont)?\s*(?:réputés\s+)?fermes?\b(?!\s+et\s+(?:révisables|actualisables))")
    neg_rev = find(sentences, r"prix\s+(?:ne\s+)?(?:sont|seront|est)\s+(?:pas|ni)\s+r[ée]visables|aucune\s+r[ée]vision\s+(?:de\s+prix\s+)?n'est\s+pr[ée]vue|pas\s+de\s+r[ée]vision")
    rev = find(sentences, r"prix\s+(?:du march[ée]\s+)?(?:sont|seront|est)\s+(?:r[ée]put[ée]s\s+)?r[ée]visables|prix\s+r[ée]visables|r[ée]vision\s+(?:annuelle\s+)?des\s+prix|les prix (?:sont|seront) r[ée]vis[ée]s")
    act = find(sentences, r"prix\s+(?:sont\s+|est\s+)?(?:fermes?\s+et\s+)?actualisables?")
    types = []
    if rev:
        types.append(("REVISABLE", rev[0][0]))
    if firm and not act:
        types.append(("FERME", firm[0][0]))
    if act:
        types.append(("FERME_ACTUALISABLE", act[0][0]))
    if neg_rev and not rev:
        types.append(("FERME", neg_rev[0][0]))
    distinct = {t for t, _ in types}
    if not types:
        f["price_type"] = not_found("price_type")
    elif len(distinct) == 1:
        f["price_type"] = make_field("price_type", types[0][0], [types[0][1]], 0.85)
    else:
        f["price_type"] = make_field("price_type", " / ".join(sorted(distinct)), [s for _, s in types], 0.5,
                                     notes=["Mentions contradictoires du type de prix (ex. prix fermes la 1re année puis révisables)."])

    # --- formule
    formula = None
    formula_rx = re.compile(r"(?<![\w])(?P<f>(?:P|Pn|P\(n\)|Pr|C|Cn|PRn?)\s*=\s*[^\n;]{3,200}?/[^\n;]{1,120})")
    f_hits = []
    for s in zone:
        for line in s.text.split("\n"):
            m = formula_rx.search(line)
            if m:
                f_hits.append((s, squash(m.group("f")).rstrip(" .,")))
    if f_hits:
        from .calculations import parse_parametric_formula
        formula = f_hits[0][1]
        parsed = parse_parametric_formula(formula)
        conf = 0.9 if parsed else 0.65
        notes = [] if parsed else ["Formule non reconnue comme paramétrique à un indice : vérification humaine requise."]
        if len({x[1] for x in f_hits}) > 1:
            conf = min(conf, 0.6)
            notes.append(f"{len({x[1] for x in f_hits})} formules différentes trouvées.")
        f["revision_formula"] = make_field("revision_formula", formula, [f_hits[0][0]], conf, notes=notes)
        f["revision_type"] = make_field("revision_type", "FORMULE_PARAMETRIQUE" if parsed else "FORMULE_A_VERIFIER",
                                        [f_hits[0][0]], conf)
    else:
        f["revision_formula"] = not_found("revision_formula")
        f["revision_type"] = not_found("revision_type")

    # --- existence de la révision
    if rev or f_hits:
        ev = [rev[0][0]] if rev else [f_hits[0][0]]
        conf = 0.9 if (rev and f_hits) else 0.75
        notes = []
        if "FERME" in distinct and "REVISABLE" in distinct:
            conf = 0.55
            notes.append("Le document mentionne aussi des prix fermes : vérifier la période d'application.")
        f["revision_exists"] = make_field("revision_exists", True, ev, conf, notes=notes)
    elif firm or neg_rev:
        s = (neg_rev or firm)[0][0]
        f["revision_exists"] = make_field("revision_exists", False, [s], 0.8 if neg_rev else 0.75,
                                          notes=["Déduit de la mention de prix fermes."] if not neg_rev else [])
    else:
        f["revision_exists"] = not_found("revision_exists")

    # --- indice
    names, ids, ev = [], [], []
    idx_name_rx = re.compile(
        r"(ICHT[-\w]*|Syntec|SYNTEC|\bBT\s?\d{2}\b|\bTP\s?\d{2}[a-z]?\b|\bFSD\s?\d\b|\bEBIQ\b|\bIPCH?\b|"
        r"indice\s+(?:des?\s+|du\s+)?(?:prix|co[uû]t)[^.;:()\n]{3,110})", re.IGNORECASE)
    idbank_rx = re.compile(r"(?:identifiant|idbank|id\s*bank|s[ée]rie|r[ée]f[ée]rence)\s*(?:insee\s*)?(?:fictif\s*)?(?:n°\s*)?:?\s*(\d{9})", re.IGNORECASE)
    for s in zone:
        flat = s.text.replace("\n", " ")
        got = False
        for m in idx_name_rx.finditer(flat):
            n = squash(m.group(1)).rstrip(" ,")
            if n.lower() not in [x.lower() for x in names]:
                names.append(n)
            got = True
        for m in idbank_rx.finditer(flat):
            if m.group(1) not in ids:
                ids.append(m.group(1))
            got = True
        if got and s not in ev:
            ev.append(s)
    if names or ids:
        f["revision_index"] = make_field("revision_index", {"names": names, "identifiers": ids}, ev[:3],
                                         0.85 if ids else 0.7,
                                         notes=[] if ids else ["Pas d'identifiant INSEE trouvé : nom d'indice à confirmer."])
    else:
        f["revision_index"] = not_found("revision_index")

    hits = find(zone, r"mois\s+z[ée]ro|mois\s+m0|indice\s+de\s+(?:base|r[ée]f[ée]rence)|\b[A-Z]{1,6}0\b[^.;=]{0,120}?valeur|valeur[^.;=]{0,120}?\b[A-Z]{1,6}0\b",
                flags=0)
    f["base_index"] = (make_field("base_index", squash(hits[0][0].text)[:300], [hits[0][0]], 0.75)
                       if hits else not_found("base_index"))

    # --- fréquence / déclencheur
    freq_map = [(r"semestr", "SEMESTRIELLE"), (r"trimestr", "TRIMESTRIELLE"), (r"mensuel", "MENSUELLE"),
                (r"annuel|une fois par an|chaque ann[ée]e|(?:à|a) chaque date anniversaire|tous les ans|par p[ée]riode de (?:douze|12) mois", "ANNUELLE")]
    found_freq = None
    for rx, lab in freq_map:
        h = find(zone, rx)
        if h:
            found_freq = (lab, h[0][0])
            break
    f["revision_frequency"] = make_field("revision_frequency", found_freq[0], [found_freq[1]], 0.8) if found_freq else not_found("revision_frequency")

    triggers, tev = [], []
    for rx, lab in [(r"(?:à|sur)\s+(?:la\s+)?demande\s+(?:écrite\s+|expresse\s+)?(?:du\s+|de\s+)?" + SUPPLIER + r"|" + SUPPLIER +
                     r"\s+(?:doit|devra|est tenu)[^.;]{0,80}?demande", "SUR_DEMANDE_DU_TITULAIRE"),
                    (r"date\s+(?:d')?anniversaire", "DATE_ANNIVERSAIRE"),
                    (r"automatiquement|de plein droit|d'office", "AUTOMATIQUE")]:
        h = find(zone, rx)
        if h:
            triggers.append(lab)
            tev.append(h[0][0])
    f["revision_trigger"] = make_field("revision_trigger", triggers, tev[:2], 0.8) if triggers else not_found("revision_trigger")

    # --- action fournisseur
    act_rx = (SUPPLIER + r"\s+(?:doit|devra|est tenu d[e'])\s*[^.;]{0,30}?(?:transmettre|adresser|pr[ée]senter|formuler|envoyer|"
              r"faire parvenir|notifier|communiquer|soumettre|demander)"
              r"|(?:à|sur)\s+(?:la\s+)?demande\s+(?:écrite\s+|expresse\s+)?(?:du\s+)?" + SUPPLIER.replace("(?:le\\s+)?", "")
              + r"|demande\s+de\s+r[ée]vision[^.;]{0,120}?" + SUPPLIER.replace("(?:le\\s+)?", "")
              + r"|" + SUPPLIER + r"[^.;]{0,60}?(?:adresse|transmet|pr[ée]sente)\s+(?:sa|une)\s+demande")
    act_hits = find(zone, act_rx)
    auto_hits = find(zone, r"r[ée]vis\w*[^.;]{0,60}(?:automatiquement|de plein droit|d'office)|(?:automatiquement|de plein droit|d'office)[^.;]{0,60}r[ée]vis")
    if act_hits:
        s = act_hits[0][0]
        f["supplier_action_required"] = make_field("supplier_action_required", True, [s], 0.85 if not auto_hits else 0.55,
                                                   notes=["Mention d'une révision automatique également présente."] if auto_hits else [])
        f["supplier_action_description"] = make_field("supplier_action_description", squash(s.text)[:400], [s], 0.85)
    elif auto_hits:
        f["supplier_action_required"] = make_field("supplier_action_required", False, [auto_hits[0][0]], 0.75)
        f["supplier_action_description"] = not_found("supplier_action_description", "Révision présentée comme automatique.")
    else:
        f["supplier_action_required"] = not_found("supplier_action_required")
        f["supplier_action_description"] = not_found("supplier_action_description")

    # --- règle de délai
    ref_rx = (r"(?P<ref>date\s+(?:d')?anniversaire|anniversaire|date\s+de\s+notification|notification|date\s+de\s+prise\s+d'effet|"
              r"date\s+(?:de\s+)?(?:d[ée]but|commencement)|date\s+de\s+r[ée]vision|date\s+d'application|[ée]ch[ée]ance)")
    dl_rx = (r"\b" + NUM + r"\s*(?P<unit>mois|jours?|semaines?)\s*(?:calendaires|francs|ouvr[ée]s|ouvrables|pleins)?\s*"
             r"(?:au\s+(?:moins|plus\s+tard)\s+)?(?P<dir>avant|apr[eè]s|à\s+compter\s+de|suivant|à\s+partir\s+de|pr[ée]c[ée]dant)\s+"
             r"(?:la\s+|le\s+|l'|chaque\s+|sa\s+)?" + ref_rx)
    dl_hits = [h for h in find(zone, dl_rx) if re.search(r"demande|transmet|adress|pr[ée]sent|formul|parvenir|notifi|r[ée]vis", h[0].text, re.I)]
    if dl_hits:
        s, m = dl_hits[0]
        amount = to_int(m.group("num"))
        unit = m.group("unit").lower()
        unit_n = "months" if unit.startswith("mois") else "days"
        if unit.startswith("semaine"):
            unit_n, amount = "days", (amount or 0) * 7
        direction = "before" if re.match(r"avant|pr[ée]c", m.group("dir"), re.I) else "after"
        ref = m.group("ref").lower()
        ref_n = "anniversary" if "anniversaire" in ref else "notification" if "notification" in ref else ref
        rule = {"amount": amount, "unit": unit_n, "direction": direction, "reference": ref_n, "text": squash(m.group(0))}
        conf = 0.85 if amount is not None else 0.5
        if len({(to_int(h[1].group("num")), h[1].group("unit")) for h in dl_hits}) > 1:
            conf = 0.55
        f["deadline_rule"] = make_field("deadline_rule", rule, [s], conf)
    else:
        f["deadline_rule"] = not_found("deadline_rule")
    f["calculated_deadline"] = not_found("calculated_deadline", "Calculée par le module de calcul.")

    # --- forclusion
    forf_rx = (r"à\s+d[ée]faut|faute\s+d[e']|pass[ée]\s+ce\s+d[ée]lai|au-del[aà]\s+de\s+ce\s+d[ée]lai|hors\s+d[ée]lai|forclos|forclusion|"
               r"ne\s+(?:pourra|peut)\s+plus\s+(?:pr[ée]tendre|se\s+pr[ée]valoir|r[ée]clamer|b[ée]n[ée]ficier|demander)|"
               r"perd(?:ra)?\s+(?:le|son|tout)\s+(?:droit|b[ée]n[ée]fice)|renonc[ée]|"
               r"(?:prix|tarifs?)\s+(?:pr[ée]c[ée]dents?|en\s+vigueur|ant[ée]rieurs?|initiaux)\s+(?:est|sont|restent|reste|seront|sera|demeurent|demeure)\s+(?:maintenus?|applicables?|appliqu[ée]s?)|"
               r"aucune\s+r[ée]vision\s+ne\s+(?:sera|pourra)|ne\s+sera\s+pas\s+r[ée]vis")
    forf_hits = [h for h in find(zone, forf_rx)
                 if re.search(r"r[ée]vis|demande|d[ée]lai|prix", h[0].text, re.I)]
    if forf_hits:
        s = forf_hits[0][0]
        f["forfeiture_exists"] = make_field("forfeiture_exists", True, [s], 0.8)
        dur = re.search(r"(?:pendant|pour)\s+(?:une\s+(?:dur[ée]e|p[ée]riode)\s+de\s+)?" + NUM + r"\s*(?P<unit>mois|ans?)|jusqu'(?:à|a)\s+la\s+(?:prochaine\s+)?date\s+anniversaire(?:\s+suivante)?", s.text, re.I)
        val = squash(s.text)[:400]
        f["forfeiture_consequence"] = make_field("forfeiture_consequence",
                                                 {"text": val, "duration": squash(dur.group(0)) if dur else None}, [s], 0.8)
    else:
        f["forfeiture_exists"] = not_found("forfeiture_exists")
        f["forfeiture_consequence"] = not_found("forfeiture_consequence")

    # --- seuil (butoir / déclenchement / sauvegarde) et plafond
    thr = find(zone, r"(clause\s+butoir|butoir|seuil|clause\s+de\s+sauvegarde|ne\s+(?:sera|pourra\s+être|est)\s+(?:appliqu[ée]e|mise\s+en\s+(?:œ|oe)uvre|d[ée]clench[ée]e)\s+que\s+si|"
                   r"si\s+la\s+variation[^.;]{0,80}?(?:sup[ée]rieure|inf[ée]rieure|exc[eè]de|d[ée]passe)|variation[^.;]{0,60}?(?:sup[ée]rieure|inf[ée]rieure)\s+à)[^.;]{0,160}?" + PCT_RE.pattern)
    if thr:
        s, m = thr[0]
        kind = "SAUVEGARDE" if re.search(r"sauvegarde|r[ée]sili", s.text, re.I) else "BUTOIR" if "butoir" in s.text.lower() else "DECLENCHEMENT"
        f["threshold_exists"] = make_field("threshold_exists", True, [s], 0.8)
        f["threshold_value"] = make_field("threshold_value", {"pct": float(m.group("pct").replace(",", ".")), "kind": kind},
                                          [s], 0.75 if kind != "DECLENCHEMENT" else 0.8,
                                          notes=["Seuil de sauvegarde : ouvre en général un droit de résiliation, pas un blocage du prix."] if kind == "SAUVEGARDE" else [])
    else:
        f["threshold_exists"] = not_found("threshold_exists")
        f["threshold_value"] = not_found("threshold_value")
    cap = find(zone, r"(plafonn[ée]e?s?|plafond|ne\s+(?:peut|pourra)\s+(?:exc[ée]der|d[ée]passer)|limit[ée]e?\s+à|dans\s+la\s+limite\s+de)[^.;]{0,80}?" + PCT_RE.pattern)
    if cap:
        s, m = cap[0]
        f["cap_exists"] = make_field("cap_exists", True, [s], 0.8)
        f["cap_value"] = make_field("cap_value", float(m.group("pct").replace(",", ".")), [s], 0.8)
    else:
        f["cap_exists"] = not_found("cap_exists")
        f["cap_value"] = not_found("cap_value")
    return f


def extract_other(sentences, docs) -> dict[str, ExtractedField]:
    f: dict[str, ExtractedField] = {}
    po = find(sentences, r"bons?\s+de\s+commande")
    po_neg = find(sentences, r"(?:n'est\s+pas|sans)\s+(?:ex[ée]cut[ée]\s+(?:au\s+moyen|par\s+(?:l'[ée]mission\s+de\s+)?)|recours\s+à)\s*(?:de\s+)?bons?\s+de\s+commande")
    if po_neg:
        f["purchase_orders_exist"] = make_field("purchase_orders_exist", False, [po_neg[0][0]], 0.75)
    elif po:
        f["purchase_orders_exist"] = make_field("purchase_orders_exist", True, [po[0][0]], 0.85)
    else:
        f["purchase_orders_exist"] = not_found("purchase_orders_exist")

    var = find(sentences, r"(?:prestations?|services?|interventions?)\s+(?:suppl[ée]mentaires|compl[ée]mentaires|ponctuelles|exceptionnelles|occasionnelles|à\s+la\s+demande|optionnelles|hors\s+forfait)"
                          r"|quantit[ée]s\s+r[ée]ellement\s+(?:ex[ée]cut[ée]es|command[ée]es|livr[ée]es|r[ée]alis[ée]es)")
    f["variable_services_exist"] = make_field("variable_services_exist", True, [var[0][0]], 0.8) if var else not_found("variable_services_exist")

    amend_docs = [d for d in docs if d.doc_type == "AMENDMENT"]
    if amend_docs:
        d = amend_docs[0]
        s0 = split_sentences(DocumentText(name=d.name, pages=d.pages[:1], has_text_layer=True))
        hit = [s for s in s0 if re.search(r"avenant", s.text, re.I)][:1]
        f["amendments_exist"] = make_field("amendments_exist", True, hit, 0.9 if hit else 0.5)
    else:
        f["amendments_exist"] = not_found("amendments_exist", "Aucun avenant fourni. Une simple mention de la possibilité d'avenant dans le CCAP n'est pas un avenant.")

    neg = find(sentences, r"(?:il\s+n'est\s+pas\s+(?:pr[ée]vu|appliqu[ée]|op[ée]r[ée]|fait\s+application)\s+d[e']\s*(?:une\s+)?|aucune\s+|pas\s+de\s+|sans\s+)retenue\s+de\s+garantie")
    pos = find(sentences, r"retenue\s+de\s+garantie")
    if neg:
        f["retention_exists"] = make_field("retention_exists", False, [neg[0][0]], 0.85)
        f["retention_rate"] = not_found("retention_rate")
        f["retention_release_rule"] = not_found("retention_release_rule")
    elif pos:
        rate = find([p[0] for p in pos], r"retenue\s+de\s+garantie[^.;]{0,80}?" + PCT_RE.pattern + r"|" + PCT_RE.pattern.replace("pct", "pct2") + r"[^.;]{0,60}?retenue\s+de\s+garantie")
        f["retention_exists"] = make_field("retention_exists", True, [pos[0][0]], 0.85)
        if rate:
            g = rate[0][1].group("pct") or rate[0][1].group("pct2")
            f["retention_rate"] = make_field("retention_rate", float(g.replace(",", ".")), [rate[0][0]], 0.8)
        else:
            f["retention_rate"] = not_found("retention_rate")
        rel = find(sentences, r"(?:retenue\s+de\s+garantie|elle)[^.;]{0,80}?(?:rembours[ée]e|restitu[ée]e|lib[ée]r[ée]e|lev[ée]e)[^.;]{0,200}")
        f["retention_release_rule"] = make_field("retention_release_rule", squash(rel[0][0].text)[:400], [rel[0][0]], 0.75) if rel else not_found("retention_release_rule")
    else:
        f["retention_exists"] = not_found("retention_exists")
        f["retention_rate"] = not_found("retention_rate")
        f["retention_release_rule"] = not_found("retention_release_rule")

    pay = find(sentences, r"d[ée]lai\s+(?:global\s+)?de\s+paiement[^.;]{0,80}?\b" + NUM + r"\s*jours")
    if pay:
        s, m = pay[0]
        f["payment_terms"] = make_field("payment_terms", {"days": to_int(m.group("num")), "text": squash(s.text)[:300]}, [s], 0.85)
    else:
        f["payment_terms"] = not_found("payment_terms")

    late = find(sentences, r"int[ée]r[eê]ts\s+moratoires|indemnit[ée]\s+forfaitaire\s+pour\s+frais\s+de\s+recouvrement")
    f["late_payment_interest"] = make_field("late_payment_interest", True, [late[0][0]], 0.8) if late else not_found("late_payment_interest")
    adv_neg = find(sentences, r"(?:aucune|pas\s+d'|il\s+n'est\s+pas\s+(?:pr[ée]vu|vers[ée]|accord[ée])\s+d')\s*avance")
    adv = find(sentences, r"\bavance\b[^.;]{0,60}(?:est|sera)\s+(?:accord[ée]e|vers[ée]e)|une\s+avance\s+(?:forfaitaire\s+)?(?:de\s+\d|est)|avance\s+forfaitaire")
    if adv_neg:
        f["advance_payment"] = make_field("advance_payment", False, [adv_neg[0][0]], 0.8)
    elif adv:
        f["advance_payment"] = make_field("advance_payment", True, [adv[0][0]], 0.75)
    else:
        f["advance_payment"] = not_found("advance_payment")
    gp = find(sentences, r"d[ée]lai\s+de\s+garantie[^.;]{0,40}?\b" + NUM + r"\s*(?P<unit>mois|ans?)\b")
    if gp:
        s_, m_ = gp[0]
        n_ = to_int(m_.group("num"))
        months_ = n_ * 12 if m_.group("unit").lower().startswith("an") else n_
        f["guarantee_period_months"] = make_field("guarantee_period_months", months_, [s_], 0.8)
    else:
        f["guarantee_period_months"] = not_found("guarantee_period_months")
    fb = find(sentences, r"(?:d[ée]compte\s+(?:g[ée]n[ée]ral|final)|projet\s+de\s+d[ée]compte|demande\s+de\s+paiement\s+du\s+solde|solde\s+du\s+march[ée])[^.;]{0,200}")
    f["final_balance_rule"] = make_field("final_balance_rule", squash(fb[0][0].text)[:400], [fb[0][0]], 0.7) if fb else not_found("final_balance_rule")
    return f


# --------------------------------------------------------------------------- avenants (P2)

def extract_amendment_price_changes(doc: DocumentText) -> list[dict]:
    """Repère "le prix unitaire de <prestation> est porté de 31,40 € HT à 33,10 € HT [à compter du …]"."""
    out = []
    rx = re.compile(r"(?P<label>[^.;:]{0,160}?)(?:est|sont)\s+(?:port[ée]s?|modifi[ée]s?|fix[ée]s?|r[ée]vis[ée]s?)\s+de\s+"
                    r"(?P<old>\d+(?:[ .]\d{3})*(?:,\d{1,2})?)\s*(?:€|euros?)\s*(?:HT|TTC)?\s+à\s+"
                    r"(?P<new>\d+(?:[ .]\d{3})*(?:,\d{1,2})?)\s*(?:€|euros?)\s*(?P<tax>HT|TTC)?", re.IGNORECASE)
    for s in split_sentences(doc):
        flat = s.text.replace("\n", " ")
        m = rx.search(flat)
        if not m:
            continue
        eff = None
        dm = re.search(r"(?:à\s+compter\s+du|à\s+partir\s+du|applicable\s+(?:au|le))\s+" + DATE_RE.pattern, flat, re.I)
        if dm:
            eff = parse_date_fr(dm)
        code = re.search(r"(?:poste|article|r[ée]f[ée]rence|code)\s*(?:n°\s*)?([A-Z0-9][\w.\-]{0,12})", m.group("label"), re.I)
        out.append({
            "label": squash(m.group("label")),
            "item_code": code.group(1) if code else None,
            "old_unit_price": parse_money(m.group("old")),
            "new_unit_price": parse_money(m.group("new")),
            "tax": m.group("tax") or "non précisé",
            "effective_date": eff.isoformat() if eff else None,
            "evidence": s.evidence(),
        })
    return out


# --------------------------------------------------------------------------- point d'entrée

FIELD_ORDER = [
    "contract_id", "buyer", "supplier", "contract_title", "contract_start_date", "contract_end_date", "annual_amount",
    "contract_duration", "price_type", "revision_exists", "revision_type", "revision_formula", "revision_index",
    "base_index", "revision_frequency", "revision_trigger", "supplier_action_required", "supplier_action_description",
    "deadline_rule", "calculated_deadline", "forfeiture_exists", "forfeiture_consequence", "cap_exists", "cap_value",
    "threshold_exists", "threshold_value", "purchase_orders_exist", "variable_services_exist", "amendments_exist",
    "retention_exists", "retention_rate", "retention_release_rule", "payment_terms", "late_payment_interest",
    "advance_payment", "guarantee_period_months", "final_balance_rule",
]


def extract_fields(docs: list[DocumentText]) -> tuple[dict[str, ExtractedField], dict[str, list]]:
    contract_docs = [d for d in docs if d.doc_type == "CONTRACT" and d.has_text_layer]
    sentences: list[Sentence] = []
    for d in contract_docs:
        sentences.extend(split_sentences(d))
    for i, s in enumerate(sentences):
        s.idx = i
    fields: dict[str, ExtractedField] = {}
    fields.update(extract_identity(contract_docs, sentences))
    fields.update(extract_amount_duration(sentences))
    fields.update(extract_price_and_revision(sentences))
    fields.update(extract_other(sentences, docs))
    amendments = {d.name: extract_amendment_price_changes(d) for d in docs if d.doc_type == "AMENDMENT" and d.has_text_layer}
    ordered = {k: fields[k] for k in FIELD_ORDER if k in fields}
    ordered.update({k: v for k, v in fields.items() if k not in ordered})
    return ordered, amendments
