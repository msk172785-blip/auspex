"""Inventaire de CONCEPTS (pas de mots-cibles) et analyseurs de valeurs.

Chaque concept est une classe sémantique décrite par des radicaux (frontière de mot en tête
pour éviter « prévision » ⊃ « révis »). Les cadres (frames.py) combinent ces concepts :
une clause « changement de prix » = OBJET_PRIX ∧ CHANGEMENT, pas « contient le mot révision ».
Les concepts sont génériques au français des marchés publics ; aucun n'est propre à un document.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

W = r"\b"


def rx(*alts: str) -> re.Pattern:
    return re.compile(W + "(?:" + "|".join(alts) + ")", re.IGNORECASE)


# ---- objets économiques
PRICE = rx(r"prix", r"tarif\w*", r"bpu\b", r"bordereaux?\s+des?\s+prix", r"conditions\s+financi[eè]res",
           r"r[ée]mun[ée]ration", r"montant\s+(?:du\s+march[ée]|forfaitaire|global)", r"redevance", r"co[uû]ts?\s+unitaires?")
CHANGE = rx(r"r[ée]vis\w*", r"ajust\w*", r"r[ée]ajust\w*", r"actualis\w*", r"[ée]volu\w*", r"variation\w*", r"vari(?:e|ent|era)\b",
            r"index\w*", r"revaloris\w*", r"mises?\s+à\s+jour", r"hausses?\b", r"augment\w*", r"baisses?\b", r"modifi\w*",
            r"nouveaux?\s+(?:prix|tarifs?)", r"nouvelles?\s+(?:conditions|grilles?)", r"coefficient\s+de\s+\w+")
INDEX = rx(r"indices?\b", r"insee\b", r"idbank", r"identifiant\s+insee", r"s[ée]ries?\s+insee")
FORMULA = re.compile(r"(?<![\w])[A-Z][A-Za-z]{0,5}\d?\s*=\s*[^\n]{0,80}?\b[A-Za-z]{1,8}\s*0\b|(?<![\w])[A-Z]\w{0,4}\s*=\s*[^\n]{0,60}/")
REEXAM = rx(r"r[ée]examen", r"imprévisib\w*", r"impr[ée]vision", r"boulevers\w*", r"R\.?\s*2194")

# ---- parties
SUPPLIER = rx(r"titulaires?", r"prestataires?", r"fournisseurs?", r"cocontractants?", r"attributaires?", r"soumissionnaires?",
              r"entreprises?\s+(?:attributaire|titulaire|retenue)")
BUYER = rx(r"acheteurs?", r"pouvoir\s+adjudicateur", r"personne\s+publique", r"administration", r"collectivit[ée]",
            r"commune", r"ma[iî]tre\s+d'ouvrage", r"entit[ée]\s+adjudicatrice", r"ville\b", r"d[ée]partement\b", r"r[ée]gion\b")

# ---- modalités
OBLIGATION = rx(r"doit\b", r"doivent\b", r"devra\b", r"devront\b", r"(?:est|sont|sera|seront)\s+tenus?\b",
                r"il\s+(?:lui\s+)?(?:appartient|incombe)", r"lui\s+(?:appartient|incombe)", r"incombe\b", r"s'engage\w*",
                r"s'oblige\w*", r"(?:est|sont)\s+obligatoires?", r"obligatoirement", r"imp[ée]rativement", r"a\s+l'obligation")
PERMISSION = rx(r"peut\b", r"peuvent\b", r"pourra\b", r"pourront\b", r"a\s+la\s+(?:possibilit[ée]|facult[ée])", r"est\s+autoris[ée]")
NEGATION = re.compile(r"\b(?:ne|n')\s*\w+\s+(?:pas|plus|aucun\w*|jamais)\b|\baucun\w*\b|\bsans\b", re.IGNORECASE)
ACTION_VERB = rx(r"transm\w+", r"adress\w+", r"envo\w+", r"pr[ée]sent\w+", r"fourni\w*", r"remet\w*", r"remis\b", r"communiqu\w+",
                 r"notifi\w+", r"demand\w+", r"formul\w+", r"calcul\w+", r"(?:faire\s+)?parven\w+", r"d[ée]pos\w+",
                 r"[ée]tabli\w*", r"soum\w+", r"inform\w+", r"signal\w+", r"factur\w+", r"[ée]met\w*", r"justifi\w+", r"produi\w+")
FUTURE_SUPPLIER_ACTION = re.compile(
    r"\b(?:le|la|les)\s+(?:titulaire|prestataire|fournisseur|cocontractant)s?\s+(?!sera\b|aura\b|pourra\b)([a-zéèêàâîôûç]+(?:era|ira|dra|ra))\b",
    re.IGNORECASE)
REQUEST = rx(r"demandes?\b", r"requ[êe]tes?", r"sollicit\w+", r"r[ée]clam\w+", r"propositions?\b")

# ---- conditions d'inaction et conséquences
INACTION_COND = rx(r"[àaÀA]\s+d[ée]faut", r"faute\s+d[e']", r"en\s+cas\s+de\s+(?:non[-\s]?\w+|retard|absence|d[ée]faut|silence)",
                   r"pass[ée]\s+(?:ce|un|le|cette|ledit)\s+d[ée]lai", r"au[-\s]del[aà]\s+d[eu]\s+(?:ce|cette|ledit)?", r"hors\s+d[ée]lai",
                   r"si\s+[^,.;]{0,60}?\bn(?:e\s+|')\s*\w+\s+pas\b", r"lorsque\s+[^,.;]{0,60}?\bn(?:e\s+|')\s*\w+\s+pas\b", r"non\s+respect[ée]",
                   r"sans\s+quoi", r"[àa]\s+peine\s+d[e']", r"par\s+son\s+silence", r"l'absence\s+de\s+r[ée]ponse",
                   r"en\s+l'absence\s+d[e']", r"sans\s+r[ée]ponse", r"non[-\s]respect", r"si\s+(?:le|la)\s+\w+\s+ne\s+\w+\s+pas")
OUT_PRICE_KEPT = re.compile(
    r"(?:\b(?:prix|tarif\w*)\b[^.;]{0,70}?\b(?:reconduit\w*|maintenu\w*|inchang\w*|rest\w*\s+(?:applicables?|en\s+vigueur|inchang\w*)|demeur\w*|fig[ée]\w*|reste\w*\s+fermes?"
    r"|continu\w*\s+(?:alors\s+|donc\s+)?(?:de|à)\s+s'appliquer|s'appliqu\w*\s+(?:toujours|encore))"
    r"|\baucune\s+(?:r[ée]vision|actualisation|augmentation|ajustement|indexation)"
    r"|\bne\s+(?:sera|seront)\s+pas\s+(?:r[ée]vis|ajust|actualis|index)\w*)", re.IGNORECASE)
OUT_RIGHT_LOST = rx(r"forclo\w*", r"d[ée]ch[ée]an\w*", r"d[ée]chu\w*", r"perd\w*\s+(?:le|son|tout|ses)\s+(?:droit|b[ée]n[ée]fice)",
                    r"ne\s+(?:pourra|peut)\s+plus\s+\w+", r"(?:r[ée]put[ée]\w*\s+(?:avoir\s+)?)?renonc\w*", r"irrecevable\w*",
                    r"abandonn\w*", r"caduc\w*")
OUT_DEEMED_ACCEPTED = rx(r"r[ée]put[ée]\w*[\s,]+(?:par\s+(?:son|leur)\s+silence[\s,]+)?(?:avoir\s+)?accept\w*",
                         r"vau\w*\s+acceptation", r"acceptation\s+tacite", r"tacitement\s+accept\w*", r"accept[ée]\w*\s+tacitement")
OUT_DEEMED_NOT_DONE = rx(r"r[ée]put[ée]\w*\s+ne\s+pas\s+avoir\s+(?:r[ée]alis|ex[ée]cut|effectu)\w*")
OUT_AUTOMATIC_FAVORABLE = rx(r"(?:sont|seront|est|sera)\s+(?:r[ée]vis|ajust|actualis|index)\w*\s+(?:automatiquement|de\s+plein\s+droit|d'office)",
                             r"(?:automatiquement|de\s+plein\s+droit|d'office)\s+(?:r[ée]vis|ajust|actualis|index)\w*")

# ---- quantités / plafonds / seuils
CAP_CUE = rx(r"plafonn\w*", r"plafonds?", r"butoir", r"maxim\w*", r"ne\s+(?:pourra|peut|saurait)\s+(?:exc[ée]der|d[ée]passer)",
             r"limit[ée]e?s?\s+à", r"dans\s+la\s+limite", r"au\s+plus\b", r"sup[ée]rieure?s?\s+à\s+(?:la\s+limite|ce\s+plafond)")
THRESHOLD_CUE = rx(r"(?:ne\s+|n')(?:sera|seront|pourra|est|sont)\s+(?:appliqu|mise?\s+en\s+(?:œ|oe)uvre|d[ée]clench|r[ée]vis|effectu)\w*\s+que\s+(?:si|lorsque|dans\s+le\s+cas)",
                   r"(?:ne\s+|n')(?:intervient|interviendra|s'applique|s'appliquera|joue|jouera)\s+que\s+(?:si|lorsque)",
                   r"seuil\s+de\s+d[ée]clenchement", r"d[ée]clench\w*", r"dès\s+lors\s+que", r"à\s+condition\s+que",
                   r"n'(?:est|intervient|interviendra)\s+que\s+si", r"seuil")
CUMULATIVE_CUE = rx(r"totalit[ée]", r"cumul\w*", r"ensemble\s+de\s+la\s+dur[ée]e", r"dur[ée]e\s+(?:totale|du\s+march[ée]|de\s+l'accord)")
ANNUAL_CUE = rx(r"annuel\w*", r"par\s+an\b", r"chaque\s+ann[ée]e", r"ann[ée]e\s+pr[ée]c[ée]dente", r"une\s+fois\s+par\s+an")
PENALTY = rx(r"p[ée]nalit\w*")
PURCHASE_ORDER = rx(r"bons?\s+de\s+commandes?", r"commandes?\b")
VARIABLE_SERVICE = rx(r"prestations?\s+(?:ponctuelles|compl[ée]mentaires|exceptionnelles|suppl[ée]mentaires|occasionnelles|optionnelles|à\s+la\s+demande)",
                      r"quantit[ée]s?\s+r[ée]ellement\s+(?:ex[ée]cut|command|livr|r[ée]alis)\w*", r"prix\s+unitaires?\s+appliqu\w*")
INVOICE = rx(r"factur\w*", r"demandes?\s+de\s+paiement", r"m[ée]moires?\b", r"d[ée]comptes?")
PAYMENT = rx(r"paiement\w*", r"r[èe]glement\w*", r"mandat\w*", r"pay[ée]\w*", r"sommes\s+dues", r"vers[ée]\w*")
CONDITION_ON = rx(r"conditionn[ée]\w*\s+(?:à|par)", r"subordonn[ée]\w*\s+à", r"sous\s+r[ée]serve\s+d[eu]", r"sur\s+pr[ée]sentation\s+d[eu]",
                  r"apr[eè]s\s+(?:validation|acceptation|admission)")
ADVANCE = rx(r"avances?\b")
RETENTION = rx(r"retenues?\s+de\s+garantie", r"retenues?\s+lib[ée]rables?", r"lib[ée]ration\s+de\s+la\s+retenue", r"restitution\s+de\s+la\s+retenue")
FINAL_BALANCE = rx(r"soldes?\b(?!\s+(?:des?\s+)?comptes?\s+bancaires?)", r"d[ée]compte\s+(?:g[ée]n[ée]ral|final|d[ée]finitif)", r"projet\s+de\s+d[ée]compte")
LATE_INTEREST = rx(r"int[ée]r[êe]ts?\s+moratoires?", r"indemnit[ée]\s+forfaitaire\s+pour\s+frais\s+de\s+recouvrement")
FREQUENCY = rx(r"annuel\w*", r"une\s+fois\s+par\s+(?:an|mois|trimestre|semestre|semaine)", r"trimestri\w*", r"semestri\w*",
               r"mensuel\w*", r"hebdomadaire\w*", r"chaque\s+(?:ann[ée]e|anniversaire|mois|trimestre)", r"à\s+chaque\s+anniversaire",
               r"tous\s+les\s+(?:ans|mois|deux\s+mois|trimestres)")
NEGATED_CHANGE = re.compile(
    r"\b(?:ne|n')\s*(?:\w+\s+){0,2}?(?:pas|plus|jamais)\s+(?:\w+\s+)?(?:r[ée]vis|ajust|actualis|index|modifi)\w*"
    r"|\bnon\s+(?:r[ée]vis|ajust|actualis|index)\w*|\baucun\w*\s+(?:r[ée]vision|actualisation|indexation|ajustement|variation)"
    r"|\bfermes?\s+et\s+d[ée]finitifs?", re.IGNORECASE)
FIRST_PERIOD_FIRM = rx(r"fermes?\s+(?:la|pendant\s+(?:la|un))\s+(?:premi[eè]re\s+ann[ée]e|an\b|un\s+an)", r"fermes?\s+pendant\s+(?:un|1)\s+an")

# ---- ancrages temporels
ANCHORS = [
    ("ANNIVERSARY", rx(r"anniversaire", r"renouvellement", r"reconduction", r"[ée]ch[ée]ance\s+annuelle", r"date\s+d'[ée]ch[ée]ance")),
    ("NOTIFICATION", rx(r"notification")),
    ("RECEIPT", rx(r"r[ée]ception")),
    ("EXECUTION_START", rx(r"d[ée]but\s+(?:d'ex[ée]cution|des\s+prestations)", r"d[ée]marrage", r"commencement", r"prise\s+d'effet", r"date\s+d'effet")),
    ("TERM_END", rx(r"terme\b", r"\bfin\s+d[eu]", r"expiration")),
    ("REPORT", rx(r"signalement", r"demande\s+de\s+la\s+collectivit[ée]", r"demande\s+de\s+l'acheteur")),
]

# ---- nombres
_UNITS = {"zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
          "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30,
          "quarante": 40, "cinquante": 50, "soixante": 60, "cent": 100}
NUM_WORD = (r"(?:\d+|(?:quatre[- ]vingt|soixante|cinquante|quarante|trente|vingt|dix|onze|douze|treize|quatorze|quinze|seize|"
            r"un|une|deux|trois|quatre|cinq|six|sept|huit|neuf)(?:[- ](?:et[- ])?(?:un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze))?)"
            r"(?:\s*\(\s*\d+\s*\))?")
NUM_RE = re.compile(r"\b" + NUM_WORD + r"(?!\w)", re.IGNORECASE)
ORDINALS = {"premi": 1, "deuxi": 2, "second": 2, "troisi": 3, "quatri": 4, "cinqui": 5}


def to_int(word: str) -> Optional[int]:
    w = word.lower().strip()
    m = re.search(r"\((\d+)\)", w)
    if m:
        return int(m.group(1))
    w = re.sub(r"\s*\(.*", "", w).strip()
    if w.isdigit():
        return int(w)
    total = 0
    for part in re.split(r"[- ]", w):
        if part in ("et", ""):
            continue
        if part == "vingt" and total == 4:  # quatre-vingt
            total = 80
            continue
        if part not in _UNITS:
            return None
        total += _UNITS[part]
    return total or None


MONTHS_FR = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8,
             "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
DATE_RE = re.compile(r"\b(\d{1,2})(?:er)?[\s/.-]+(\d{1,2}|" + "|".join(MONTHS_FR) + r")[\s/.-]+(\d{4})\b", re.IGNORECASE)
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS_FR) + r")\b(?!\s+\d{4})", re.IGNORECASE)
MONEY_RE = re.compile(r"(?<![\d,.])(\d{1,3}(?:[  .]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|euros?\b)\s*(HT|H\.T\.?|TTC|T\.T\.C\.?)?",
                      re.IGNORECASE)
PCT_RE = re.compile(r"(?<![\d,.])(\d+(?:[,.]\d+)?)\s*(?:%|pour\s*cent\b)", re.IGNORECASE)
DURATION_RE = re.compile(r"(" + NUM_WORD + r")\s*(mois|jours?|semaines?|ans?|ann[ée]es?|heures?)\b"
                         r"(?:\s+(calendaires|francs|ouvr[ée]s|ouvrables|pleins|ouvrables))?", re.IGNORECASE)


def parse_date(m: re.Match) -> Optional[date]:
    try:
        mo = m.group(2).lower()
        return date(int(m.group(3)), int(mo) if mo.isdigit() else MONTHS_FR[mo], int(m.group(1)))
    except (ValueError, KeyError):
        return None


def parse_money(s: str) -> float:
    return float(re.sub(r"[  .]", "", s).replace(",", "."))


def unit_norm(u: str) -> str:
    u = u.lower()
    if u.startswith("mois"):
        return "months"
    if u.startswith("an"):
        return "years"
    if u.startswith("semaine"):
        return "weeks"
    if u.startswith("heure"):
        return "hours"
    return "days"


def party_mentions(text: str) -> list[tuple[int, str]]:
    out = [(m.start(), "SUPPLIER") for m in SUPPLIER.finditer(text)] + [(m.start(), "BUYER") for m in BUYER.finditer(text)]
    return sorted(out)
