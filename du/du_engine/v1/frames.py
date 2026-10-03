"""Interpréteur sémantique LOCAL par cadres (frame semantics), déterministe et hors ligne.

Il ne cherche pas un mot cible : il compose des concepts (lexicon.py) au niveau phrase / section :
  - changement de prix  = OBJET_PRIX ∧ CHANGEMENT ∧ mécanisme (formule, indice, verbe appliqué aux prix)
  - obligation          = MODALITÉ DÉONTIQUE (ou futur d'obligation) ∧ VERBE D'ACTION ∧ ACTEUR (explicite, pronom, inféré)
  - délai               = DURÉE ∧ RELATION (avant/après/à compter de) ∧ ÉVÉNEMENT D'ANCRAGE (classe d'événement)
  - conséquence         = CONDITION D'INACTION ∧ ISSUE (prix maintenus, droit perdu, acceptation réputée…) ∧ POLARITÉ
  - rôle d'un nombre    = gouverneur sémantique local (plafond/seuil/BDC/avance/pénalité…)
Les interprétations produites sont ensuite VÉRIFIÉES contre le texte (verify.py) : ce module ne prouve rien.
"""
from __future__ import annotations

import re
from typing import Optional

from . import lexicon as L
from .document import Sentence, StructuredDocument, squash
from .schema import Amount, Clause, Evidence, Percentage

PRICE_MECHANISM = re.compile(
    r"\b(?:fera|feront|font|fait)\s+l'objet\s+d'une?\s+(?:r[ée]vision|actualisation|ajustement|indexation|r[ée]vision\s+annuelle)"
    r"|\b(?:sont|seront|est|sera)\s+(?:r[ée]vis|ajust|actualis|index|r[ée]ajust|revaloris)\w*"
    r"|\b(?:r[ée]visables?|actualisables?|ajustables?|indexables?|indexé\w*)\b"
    r"|\b(?:r[ée]vision|actualisation|ajustement|indexation|variation|[ée]volution)\s+(?:annuelle\s+)?(?:des|du)\s+(?:prix|tarifs?)"
    r"|\b(?:mise\s+à\s+jour|ajustement\s+tarifaire)\b|\bnouveaux?\s+(?:prix|tarifs?|bordereaux?)\b|\bnouvelles?\s+grilles?\s+tarifaires?", re.IGNORECASE)
RELATION = re.compile(r"\s*(?:au\s+(?:moins|plus\s+tard|minimum|maximum)\s+)?(avant|apr[eè]s|à\s+compter\s+d[eu']?|suivant|courant\s+à\s+compter\s+d[eu']?|"
                      r"à\s+partir\s+d[eu']?|pr[ée]c[ée]dant|qui\s+suiv\w+|au\s+plus\s+tard\s+avant)\s*(?P<anchor>[^.;]{2,140})", re.IGNORECASE)
ANAPHORA = re.compile(r"\b(?:ce|cet|cette|ces|ledit|ladite|lesdits|lesdites|tel|telle)\s+(?:d[ée]lai|notification|montant|demande|date|prix|communication|transmission|r[ée]ponse)\b",
                      re.IGNORECASE)
PRONOUN = re.compile(r"(?:^|[\s,;:(])(?:il|elle|ils|elles|lui|leur)\b", re.IGNORECASE)


class FrameInterpreter:
    name = "FRAMES"

    def __init__(self, sd: StructuredDocument):
        self.sd = sd
        self.sents = sd.sentences

    # ------------------------------------------------------------------ utilitaires
    def _flat(self, s: Sentence) -> str:
        return squash(s.text)

    def _ev(self, *sents: Sentence) -> list[Evidence]:
        out = []
        for s in sents:
            sec = self.sd.section(s.section)
            out.append(Evidence(document=self.sd.name, page=s.page, page_end=s.page_end, article=sec.number,
                                quote=self._flat(s)))
        return out

    def _section_sents(self, sid: str) -> list[Sentence]:
        return [s for s in self.sents if s.section == sid]

    def _prev(self, s: Sentence, n: int = 3) -> list[Sentence]:
        return [x for x in self.sents[max(0, s.idx - n):s.idx] if x.section == s.section]

    def _base(self, etype: str, sents: list[Sentence], conf: float) -> Clause:
        sec = self.sd.section(sents[0].section)
        return Clause(event_type=etype, evidence=self._ev(*sents), section_id=sec.sid, source_page=sents[0].page,
                      source_article=sec.number, source_quote=self._flat(sents[0]), interpreter=self.name, confidence=conf)

    # ------------------------------------------------------------------ acteur
    def resolve_actor(self, s: Sentence, anchor_pos: Optional[int] = None) -> tuple[str, str]:
        t = self._flat(s)
        pos = anchor_pos if anchor_pos is not None else len(t)
        before = [p for p in L.party_mentions(t) if p[0] < pos]
        pron = [m.start() for m in PRONOUN.finditer(t[:pos])]
        if before and (not pron or before[-1][0] > pron[-1]):
            return before[-1][1], "EXPLICIT"
        if pron:
            if before:
                return before[-1][1], "PRONOUN"
            subj = self._subject_of_previous(s)
            if subj:
                return subj, "PRONOUN"
        agent = re.search(r"\b(?:par|du|de\s+la\s+part\s+d[ue']?)\s+(?:le\s+|la\s+|l')?(titulaire|prestataire|fournisseur|acheteur|pouvoir\s+adjudicateur|"
                          r"administration|commune|collectivit[ée]|personne\s+publique)", t, re.IGNORECASE)
        if agent:
            return ("SUPPLIER" if L.SUPPLIER.match(agent.group(1)) else "BUYER"), "EXPLICIT"
        # voix passive : un envoi ADRESSÉ À une partie est fait par l'autre partie
        rcpt = re.search(r"\b(?:adress|transmi|remi|notifi|envoy|communiqu|parven|présent)\w*\s+(?:par\s+\w+\s+)?(?:à\s+l'|à\s+la\s+|au\s+|aux\s+)"
                         r"(acheteur|pouvoir\s+adjudicateur|administration|collectivit[ée]|commune|personne\s+publique|ma[iî]tre\s+d'ouvrage|"
                         r"titulaire|prestataire|fournisseur)", t, re.IGNORECASE)
        if rcpt:
            return ("BUYER" if L.SUPPLIER.match(rcpt.group(1)) else "SUPPLIER"), "INFERRED_FROM_RECIPIENT"
        # voix passive sans agent : inférence depuis la section (ex. « sa demande » rattachée au titulaire)
        if L.REQUEST.search(t):
            for o in self._section_sents(s.section):
                ft = self._flat(o)
                if o.idx != s.idx and L.REQUEST.search(ft) and re.search(r"\b(?:sa|son|ses)\s+demande", ft, re.IGNORECASE):
                    pm = L.party_mentions(ft)
                    if pm:
                        return pm[0][1], "INFERRED_FROM_SECTION"
            for o in self._section_sents(s.section):
                if L.party_mentions(self._flat(o)) and o.idx != s.idx and L.OBLIGATION.search(self._flat(o)):
                    return L.party_mentions(self._flat(o))[0][1], "INFERRED_FROM_SECTION"
        return "UNKNOWN", "NONE"

    def _subject_of_previous(self, s: Sentence, depth: int = 3) -> Optional[str]:
        """Antécédent d'un pronom sujet : le SUJET de la phrase précédente (première partie citée),
        en remontant la chaîne si cette phrase commence elle-même par un pronom."""
        prev = self._prev(s, 1)
        if not prev or depth == 0:
            return None
        pt = self._flat(prev[-1])
        if re.match(r"^(?:[^,]{0,60},\s*)?(?:il|elle|ils|elles)\b", pt, re.IGNORECASE):
            return self._subject_of_previous(prev[-1], depth - 1)
        pm = L.party_mentions(pt)
        return pm[0][1] if pm else None

    # ------------------------------------------------------------------ délais
    def parse_deadlines(self, text: str) -> list[dict]:
        out = []
        for m in L.DURATION_RE.finditer(text):
            amount = L.to_int(m.group(1))
            rel = RELATION.match(text, m.end())
            if not rel or amount is None:
                continue
            anchor_text = squash(rel.group("anchor"))[:120]
            anchor = "OTHER"
            for name, pat in L.ANCHORS:
                if pat.search(anchor_text):
                    anchor = name
                    break
            direction = "before" if re.match(r"avant|pr[ée]c|au\s+plus\s+tard\s+avant", rel.group(1), re.IGNORECASE) else "after"
            out.append({"amount": amount, "unit": L.unit_norm(m.group(2)), "qualifier": (m.group(3) or "").lower() or None,
                        "direction": direction, "anchor": anchor, "anchor_text": anchor_text,
                        "text": squash(text[m.start():rel.end()])[:200]})
        for m in re.finditer(r"(?:au\s+plus\s+tard\s+le|avant\s+le|d'ici\s+le|jusqu'au)\s+(\d{1,2})(?:er)?\s+(" + "|".join(L.MONTHS_FR) + r")\b(?!\s+\d{4})", text, re.IGNORECASE):
            out.append({"amount": None, "unit": "fixed_day", "direction": "before", "anchor": "FIXED_DAY",
                        "anchor_text": squash(m.group(0)), "day": int(m.group(1)), "month": L.MONTHS_FR[m.group(2).lower()],
                        "text": squash(m.group(0))})
        return out

    # ------------------------------------------------------------------ rôles des nombres
    def classify_amount(self, text: str, m: re.Match) -> str:
        before = text[max(0, m.start() - 160):m.start()].lower()
        after = text[m.end():m.end() + 60].lower()
        window = before + " " + after
        if re.search(r"\bport[ée]\w*\s+de\s*$", before):
            return "OLD_UNIT_PRICE"
        if re.search(r"\bport[ée]\w*\s+de\s+[\d ,.]+\s*(?:€|euros?)\s*(?:ht|ttc)?\s+à\s*$", before):
            return "NEW_UNIT_PRICE"
        if re.search(r"\bpar\s+(?:jour|heure|constat|site|planning|personne|d[ée]sordre|renouvellement|heure\s+d'insertion)", after) or \
                (L.PENALTY.search(window) and re.search(r"\bpar\b", after)):
            return "PENALTY_RATE"
        if L.PENALTY.search(before) and re.search(r"ne\s+d[ée]passe\s+pas|inf[ée]rieur", before):
            return "PENALTY_EXEMPTION_THRESHOLD"
        if re.search(r"sous[-\s]trait", window) and re.search(r"sup[ée]rieur", before):
            return "SUBCONTRACT_DIRECT_PAYMENT_THRESHOLD"
        if L.ADVANCE.search(window) and re.search(r"sup[ée]rieur|d'un\s+montant", before):
            return "ADVANCE_ELIGIBILITY_THRESHOLD"
        if L.RETENTION.search(window):
            return "RETENTION_AMOUNT"
        if re.search(r"commandes?\b", before) and re.search(r"maxim|plafond", before):
            return "PURCHASE_ORDER_ANNUAL_CEILING" if re.search(r"annuel", before) else "CONTRACT_CEILING"
        if re.search(r"commandes?\b", before) and re.search(r"minim", before):
            return "PURCHASE_ORDER_ANNUAL_MINIMUM"
        if re.search(r"montant\s+(?:annuel|global|total)[^.;]{0,60}(?:du\s+march[ée]|estimat|estim[ée])|montant\s+(?:estimatif|estim[ée])\s+annuel", before) \
                and not re.search(r"commande|maxim|minim", before[-80:]):
            return "ANNUAL_CONTRACT_VALUE"
        if re.search(r"prix\s+unitaire", before[-60:]):
            return "UNIT_PRICE"
        return "OTHER"

    def classify_percentage(self, text: str, m: re.Match, section_title: str) -> tuple[str, str]:
        before = text[max(0, m.start() - 180):m.start()]
        after = text[m.end():m.end() + 80]
        window = text[:m.start()] + " " + after
        ctx_all = window + " " + section_title
        if L.ADVANCE.search(window) and re.search(r"rembours", window, re.IGNORECASE):
            return "OTHER", "ADVANCE_REPAYMENT"
        if L.ADVANCE.search(window):
            return "OTHER", "ADVANCE_RATE"
        if L.RETENTION.search(window):
            return "OTHER", "RETENTION_RATE"
        if L.PENALTY.search(window):
            return "PENALTY", "OTHER"
        if re.search(r"pris\w*\s+en\s+charge|prise\s+en\s+charge|support[ée]", window, re.IGNORECASE):
            return "OTHER", "COST_SHARE"
        if re.search(r"montant\s+de\s+la\s+modification|modification\s+sup[ée]rieure|montant\s+du\s+march[ée]\s+initial", window, re.IGNORECASE):
            return "OTHER", "MODIFICATION_CAP"
        price_ctx = L.PRICE.search(ctx_all) or L.CHANGE.search(ctx_all)
        cap = L.CAP_CUE.search(ctx_all)
        thr = L.THRESHOLD_CUE.search(window)
        if re.search(r"sauvegarde", section_title, re.IGNORECASE):
            return "THRESHOLD", "SAFEGUARD"
        if price_ctx and cap:
            # un plafond peut être annuel ET un autre cumulé : on qualifie chaque pourcentage par son contexte immédiat
            near = (before[-110:] + " " + after[:60])
            if L.CUMULATIVE_CUE.search(near):
                return "CAP", "CAP_CUMULATIVE"
            return "CAP", "CAP_ANNUAL" if L.ANNUAL_CUE.search(near) or L.ANNUAL_CUE.search(window) else "OTHER"
        if price_ctx and thr:
            return "THRESHOLD", "TRIGGER_THRESHOLD"
        return "OTHER", "OTHER"

    # ------------------------------------------------------------------ cadres
    def interpret(self) -> list[Clause]:
        clauses: list[Clause] = []
        clauses += self.frame_price_change()
        clauses += self.frame_consequences()
        clauses += self.frame_percent_limits()
        clauses += self.frame_purchase_orders()
        clauses += self.frame_billing_and_payment()
        clauses += self.frame_other_rights()
        return clauses

    def _price_subject(self, s: Sentence) -> bool:
        """Objet « prix » explicite, ou pronom sujet dont l'antécédent (phrase précédente de la section) est un prix."""
        t = self._flat(s)
        if L.PRICE.search(t):
            return True
        if re.match(r"^(?:[^,]{0,60},\s*)?(?:ils|elles|il|elle)\b", t, re.IGNORECASE):
            prev = self._prev(s, 1)
            return bool(prev and L.PRICE.search(self._flat(prev[-1])))
        return False

    def _is_price_change(self, t: str, s: Optional[Sentence] = None) -> bool:
        if L.REEXAM.search(t) or (s is not None and L.REEXAM.search(self.sd.section(s.section).title)):
            return False
        if L.NEGATED_CHANGE.search(t) and not L.FORMULA.search(t):
            return False  # « prix fermes et non révisables », « aucune actualisation » : prix ferme, pas un mécanisme
        mech = PRICE_MECHANISM.search(t)
        price = L.PRICE.search(t) or (s is not None and self._price_subject(s))
        return bool((price and L.CHANGE.search(t) and mech) or L.FORMULA.search(t)
                    or (L.INDEX.search(t) and (price or L.CHANGE.search(t))))

    def price_sections(self) -> list[str]:
        out = []
        for sec in self.sd.sections:
            title = sec.title
            sents = self._section_sents(sec.sid)
            title_change = bool(L.CHANGE.search(title) and (L.PRICE.search(title) or re.search(r"r[ée]vision|actualisation|indexation|ajustement|variation|[ée]volution", title, re.I)))
            mech = sum(1 for s in sents if self._is_price_change(self._flat(s), s))
            req_change = any(L.REQUEST.search(self._flat(x)) and L.CHANGE.search(self._flat(x)) for x in sents)
            if (title_change and not L.REEXAM.search(title) and not L.CAP_CUE.search(title)) or mech >= 2 or (mech >= 1 and req_change):
                out.append(sec.sid)
        return out

    def frame_price_change(self) -> list[Clause]:
        clauses = []
        psecs = self.price_sections()
        # 1) mécanisme du nouveau prix : phrases « mécanisme » dans les sections de prix, et renvois ailleurs
        mech_sents = [s for s in self.sents if (self._is_price_change(self._flat(s), s)
                      or (s.section in psecs and L.PRICE.search(self._flat(s)) and L.FIRST_PERIOD_FIRM.search(self._flat(s))))
                      and not L.CAP_CUE.search(self._flat(s)) and not L.INACTION_COND.search(self._flat(s))]
        for s in mech_sents:
            t = self._flat(s)
            c = self._base("PRICE_REVISION", [s], 0.8 if s.section in psecs else 0.7)
            f = L.FORMULA.search(t)
            if f:
                fm = re.search(r"(?<![\w])([A-Z][A-Za-z]{0,5}\d?\s*=\s*[^\n−–]{3,80}?\))", s.text) or re.search(r"(?<![\w])([A-Z][A-Za-z]{0,5}\s*=\s*[^\n]{3,80})", s.text)
                c.attributes["formula"] = squash(fm.group(1)) if fm else squash(f.group(0))
            ids = re.findall(r"(?:identifiant|idbank|s[ée]rie)\W+(?:[A-Za-zÀ-ÿ°]+\W+){0,2}?(\d{9})\b", t, re.IGNORECASE)
            if ids:
                c.attributes["index_identifiers"] = sorted(set(ids))
            nm = re.search(r"\b(indices?\s+(?:des?\s+|du\s+)?(?:prix|co[uû]t)[^.;:()\n-]{3,120}|Syntec|ICHT[-\w]*|\bBT\s?\d{2}\b|\bTP\s?\d{2}\b)", t, re.IGNORECASE)
            if nm:
                c.attributes["index_name"] = squash(nm.group(1))[:140]
            if L.FIRST_PERIOD_FIRM.search(t):
                c.attributes["first_period_firm"] = True
            if re.search(r"anniversaire|annuel\w*|chaque\s+ann[ée]e|une\s+fois\s+par\s+an", t, re.IGNORECASE):
                c.attributes["revision_frequency"] = "ANNUAL"
            if re.search(r"facturation|factur", t, re.IGNORECASE) and re.search(r"mise\s+à\s+jour|appliqu|r[ée]vis", t, re.IGNORECASE):
                c.attributes["application_timing"] = t[:240]
            if re.search(r"\breconduction\b", t, re.IGNORECASE):
                c.attributes["applies_from"] = "RENEWAL_PERIODS"
            c.trigger = "ON_REQUEST" if any(L.REQUEST.search(self._flat(x)) and L.CHANGE.search(self._flat(x))
                                            for x in self._section_sents(s.section)) else ""
            if L.OUT_AUTOMATIC_FAVORABLE.search(t) and not L.INACTION_COND.search(t):
                c.trigger = "AUTOMATIC"
            c.attributes["in_price_section"] = s.section in psecs
            clauses.append(c)

        # 2) délais et actions du titulaire dans les sections de changement de prix
        for sid in psecs:
            for s in self._section_sents(sid):
                t = self._flat(s)
                dls = [d for d in self.parse_deadlines(t)]
                is_request = L.REQUEST.search(t) or L.ACTION_VERB.search(t)
                if dls and is_request and not L.INACTION_COND.search(t[:40]):
                    pos = L.OBLIGATION.search(t)
                    actor, basis = self.resolve_actor(s, pos.start() if pos else None)
                    c = self._base("PRICE_REVISION_DEADLINE", [s], 0.85 if basis == "EXPLICIT" else 0.75)
                    c.deadline_rule = dls[0]
                    c.deadline_basis = dls[0]["anchor"]
                    c.actor, c.actor_basis = actor, basis
                    c.action_required = t[:300]
                    if re.search(r"lettre\s+recommand\w+|accus[ée]\s+de\s+r[ée]ception|LRAR", t, re.IGNORECASE):
                        c.attributes["form"] = "LETTRE_RECOMMANDEE_AR"
                    if basis != "EXPLICIT":
                        c.review_reasons.append(f"Acteur non explicite dans la phrase (base : {basis}).")
                    clauses.append(c)
                obl = L.OBLIGATION.search(t)
                fut = L.FUTURE_SUPPLIER_ACTION.search(t)
                verb_pos = obl.start() if obl else (fut.start(1) if fut else 0)
                if (obl or fut) and L.ACTION_VERB.search(t) and not L.PERMISSION.search(t[:verb_pos]):
                    actor, basis = self.resolve_actor(s, verb_pos)
                    if actor == "SUPPLIER":
                        c = self._base("SUPPLIER_ACTION_REQUIRED", [s], 0.85 if basis == "EXPLICIT" else 0.75)
                        c.actor, c.actor_basis = actor, basis
                        c.action_required = t[:300]
                        c.attributes["modality"] = "FUTURE_INDICATIVE" if fut and not obl else "DEONTIC"
                        c.attributes["related_to"] = "PRICE_REVISION"
                        if dls:
                            c.deadline_rule = dls[0]
                        clauses.append(c)
        return clauses

    def frame_consequences(self) -> list[Clause]:
        clauses = []
        psecs = set(self.price_sections())
        for s in self.sents:
            t = self._flat(s)
            cond = L.INACTION_COND.search(t)
            outcomes = [(k, p.search(t)) for k, p in (("PRICE_KEPT", L.OUT_PRICE_KEPT), ("DEEMED_ACCEPTED", L.OUT_DEEMED_ACCEPTED),
                                                      ("DEEMED_NOT_PERFORMED", L.OUT_DEEMED_NOT_DONE), ("RIGHT_LOST", L.OUT_RIGHT_LOST))]
            outcomes = [(k, m) for k, m in outcomes if m]
            if not outcomes:
                continue
            kind, om = outcomes[0]
            silence = re.search(r"silence|absence\s+de\s+r[ée]ponse|sans\s+r[ée]ponse|tacite", t, re.IGNORECASE)
            cond_sent = None
            if not cond and not silence and kind != "DEEMED_ACCEPTED":
                prev = self._prev(s, 1)
                pc = L.INACTION_COND.search(self._flat(prev[-1])) if prev else None
                if pc and (re.search(r"\b(?:alors|dans\s+ce\s+cas|en\s+pareil\s+cas|de\s+ce\s+fait|dès\s+lors)\b", t, re.I) or kind == "PRICE_KEPT"):
                    cond, cond_sent = pc, prev[-1]
                else:
                    continue
            # partie inactive : celle dont l'inaction déclenche l'issue
            seg = t[:om.start()] if om else t
            parties = L.party_mentions(seg)
            basis_ = "EXPLICIT"
            if kind == "DEEMED_ACCEPTED":
                m_acc = re.search(r"r[ée]put[ée]", t, re.IGNORECASE)
                silent = re.search(r"(?:absence\s+de\s+r[ée]ponse|silence)[^.;]{0,40}?(?:de\s+la\s+part\s+d[eu']\s*|d[eu']\s*)?(?:l'|la\s+|le\s+)?(\w[\w\s']{0,30})", t, re.IGNORECASE)
                if m_acc:
                    p = L.party_mentions(t[:m_acc.start()])
                    inactive = p[-1][1] if p else "UNKNOWN"
                elif silent:
                    p = L.party_mentions(silent.group(0))
                    inactive = p[-1][1] if p else "UNKNOWN"
                else:
                    inactive = parties[-1][1] if parties else "UNKNOWN"
                polarity = {"SUPPLIER": "UNFAVORABLE", "BUYER": "FAVORABLE"}.get(inactive, "UNKNOWN")
            elif kind == "PRICE_KEPT":
                inactive = "SUPPLIER" if (parties and parties[-1][1] == "SUPPLIER") or s.section in psecs else (parties[-1][1] if parties else "UNKNOWN")
                polarity = "UNFAVORABLE"
            else:
                # la partie qui subit la conséquence est celle qui devait agir : sujet explicite après la condition,
                # sinon l'obligé de l'obligation non remplie (même phrase avant la condition, ou phrase antécédente)
                after_cond = t[cond.end():om.start()] if cond and om and cond.end() < om.start() else ""
                pm_after = L.party_mentions(after_cond)
                if pm_after:
                    inactive, basis_ = pm_after[0][1], "EXPLICIT"
                elif cond and cond.start() > 20 and (L.OBLIGATION.search(t[:cond.start()]) or L.REQUEST.search(t[:cond.start()])):
                    inactive, basis_ = self.resolve_actor(s, L.OBLIGATION.search(t[:cond.start()]).start() if L.OBLIGATION.search(t[:cond.start()]) else cond.start())
                else:
                    inactive, basis_ = self.resolve_actor(s, om.start() if om else None)
                polarity = "UNFAVORABLE" if inactive == "SUPPLIER" else ("FAVORABLE" if inactive == "BUYER" and kind != "DEEMED_NOT_PERFORMED" else "UNKNOWN")
            economic = (s.section in psecs or L.PRICE.search(t) or L.INVOICE.search(t) or L.PAYMENT.search(t)
                        or re.search(r"\bmontant", t, re.IGNORECASE) or kind in ("DEEMED_NOT_PERFORMED",))
            if not economic:
                continue
            ev_sents = [s]
            ante = None
            anchor_s = cond_sent or s
            if ANAPHORA.search(t) or cond:
                prevs = list(reversed(self._prev(anchor_s, 4)))
                ante = next((p for p in prevs if self.parse_deadlines(self._flat(p))), None) or \
                    next((p for p in prevs if re.search(r"notifi|d[ée]lai", self._flat(p), re.IGNORECASE)), None)
            ev_sents = [x for x in (ante, cond_sent, s) if x is not None]
            c = self._base("CONSEQUENCE_IF_NO_ACTION", ev_sents, 0.8)
            c.source_quote = t
            c.source_page = s.page
            c.consequence_if_no_action = {"type": kind, "polarity_for_supplier": polarity, "inactive_party": inactive,
                                          "text": t[:300], "condition": squash(cond.group(0)) if cond else (silence.group(0) if silence else "")}
            dur = re.search(r"pour\s+une\s+(?:nouvelle\s+)?p[ée]riode\s+d[e']\s*(" + L.NUM_WORD + r")\s*(ans?|mois|ann[ée]es?)", t, re.IGNORECASE)
            if dur:
                c.consequence_if_no_action["duration"] = {"amount": L.to_int(dur.group(1)), "unit": L.unit_norm(dur.group(2))}
            c.attributes["related_to"] = "PRICE_REVISION" if (s.section in psecs or (L.PRICE.search(t) and L.CHANGE.search(t)) or kind == "PRICE_KEPT") \
                else ("INVOICE" if L.INVOICE.search(self._flat(ante) if ante else "") or L.INVOICE.search(t) or re.search(r"\bmontant", t, re.I) else "OTHER")
            if ante:
                dl = self.parse_deadlines(self._flat(ante)) or self.parse_deadlines(t)
            else:
                dl = self.parse_deadlines(t)
            if dl:
                c.deadline_rule = dl[0]
                c.deadline_basis = dl[0]["anchor"]
            c.actor = inactive
            c.actor_basis = basis_ if inactive != "UNKNOWN" else "NONE"
            if c.actor_basis == "PRONOUN":
                c.review_reasons.append("Partie inactive déduite d'un pronom.")
            if ante is not None and c.deadline_rule and not self.parse_deadlines(t):
                c.review_reasons.append("Délai hérité d'une phrase précédente par anaphore (« ce délai ») : rattachement à confirmer.")
            if inactive == "UNKNOWN":
                c.review_reasons.append("Partie inactive non identifiée.")
            if kind == "PRICE_KEPT" and re.search(r"d'office|automatiquement|de\s+plein\s+droit", t, re.IGNORECASE):
                c.attributes["note"] = "« d'office/automatiquement » décrit ici la conséquence de l'inaction (prix NON révisés), pas une révision automatique."
            clauses.append(c)
        return clauses

    def frame_percent_limits(self) -> list[Clause]:
        clauses = []
        for sec in self.sd.sections:
            sents = self._section_sents(sec.sid)
            if re.search(r"sauvegarde", sec.title, re.IGNORECASE) and sents:
                c = self._base("PRICE_REVISION_THRESHOLD", sents[:1], 0.75)
                c.attributes["kind"] = "SAFEGUARD"
                c.consequence_if_action = self._flat(sents[0])[:300]
                c.actor = "BUYER" if L.BUYER.search(self._flat(sents[0])) else "UNKNOWN"
                clauses.append(c)
            for s in sents:
                t = self._flat(s)
                pcts = list(L.PCT_RE.finditer(t))
                if not pcts:
                    continue
                items = []
                for m in pcts:
                    role, sub = self.classify_percentage(t, m, sec.title)
                    items.append(Percentage(value=float(m.group(1).replace(",", ".")), role=role, subrole=sub, raw=m.group(0)))
                limits = [p for p in items if p.role in ("CAP", "THRESHOLD")]
                if not limits:
                    continue
                c = self._base("PRICE_REVISION_THRESHOLD", [s], 0.85)
                c.percentages = items
                c.attributes["kind"] = "+".join(sorted({p.subrole if p.subrole != "OTHER" else p.role for p in limits}))
                if any(p.subrole == "OTHER" for p in limits):
                    c.review_reasons.append("Plafond sans qualification annuelle/cumulée explicite.")
                clauses.append(c)
        return clauses

    def frame_purchase_orders(self) -> list[Clause]:
        clauses = []
        po_sents = [s for s in self.sents if L.PURCHASE_ORDER.search(self._flat(s)) and re.search(r"bons?\s+de\s+commande", self._flat(s), re.I)]
        if po_sents:
            amounts, chosen = [], [po_sents[0]]
            for s in po_sents:
                t = self._flat(s)
                for m in L.MONEY_RE.finditer(t):
                    role = self.classify_amount(t, m)
                    if role.startswith("PURCHASE_ORDER") or role == "CONTRACT_CEILING":
                        amounts.append(Amount(value=L.parse_money(m.group(1)), unit=f"EUR {m.group(2) or ''}".strip(), role=role, raw=m.group(0)))
                        if s not in chosen:
                            chosen.append(s)
            c = self._base("PURCHASE_ORDER_BILLING", chosen, 0.85)
            c.amounts = amounts
            c.action_required = "Facturer chaque bon de commande exécuté (prix du BPU appliqués aux quantités réellement exécutées)."
            c.actor = "SUPPLIER"
            c.actor_basis = "INFERRED_FROM_SECTION"
            clauses.append(c)
        var = [s for s in self.sents if L.VARIABLE_SERVICE.search(self._flat(s))]
        if var:
            c = self._base("VARIABLE_SERVICE_BILLING", var[:2], 0.8)
            clauses.append(c)
        return clauses

    def frame_billing_and_payment(self) -> list[Clause]:
        clauses = []
        for s in self.sents:
            t = self._flat(s)
            cm = L.CONDITION_ON.search(t)
            if cm and L.INVOICE.search(t[:cm.start()]) and not L.PENALTY.search(t) \
                    and not re.match(r"\s*(?:la\s+|une\s+|des\s+|d'une\s+)?(?:facture|m[ée]moire|demande\s+de\s+paiement)", t[cm.end():], re.IGNORECASE):
                c = self._base("BILLING_CONDITION", [s], 0.8)
                c.trigger = squash(t[L.CONDITION_ON.search(t).start():])[:240]
                who = re.search(r"(?:transmis|établi|fourni|remis)\w*\s+par\s+(?:le\s+|la\s+)?(\w+)", t, re.IGNORECASE)
                c.actor = "SUPPLIER" if who and L.SUPPLIER.search(who.group(1)) else ("SUPPLIER" if L.SUPPLIER.search(t) else "UNKNOWN")
                c.actor_basis = "EXPLICIT" if L.SUPPLIER.search(t) else "NONE"
                c.action_required = "Satisfaire la condition préalable à la facturation : " + c.trigger
                clauses.append(c)
            if L.PAYMENT.search(t) and re.search(r"d[ée]lai", t, re.IGNORECASE):
                dls = [d for d in self.parse_deadlines(t) if d["unit"] == "days"]
                if dls and re.search(r"paiement|sommes\s+dues|r[èe]glement|mandat", t, re.IGNORECASE) and not L.PENALTY.search(t):
                    c = self._base("PAYMENT_TERM", [s], 0.85)
                    c.deadline_rule = dls[0]
                    c.deadline_basis = dls[0]["anchor"]
                    c.actor = "BUYER"
                    c.actor_basis = "INFERRED_FROM_SECTION"
                    clauses.append(c)
            if L.LATE_INTEREST.search(t) and not re.search(r"\baucun\w*\s+int[ée]r[êe]t", t, re.IGNORECASE):
                c = self._base("LATE_PAYMENT_INTEREST", [s], 0.8)
                clauses.append(c)
        return clauses

    def frame_other_rights(self) -> list[Clause]:
        clauses = []
        for sec in self.sd.sections:
            sents = self._section_sents(sec.sid)
            if not sents:
                continue
            title = sec.title
            # avance
            if L.ADVANCE.search(title) or any(L.ADVANCE.search(self._flat(s)) and re.search(r"mandat|vers|accord|pr[ée]vu", self._flat(s), re.I) for s in sents):
                adv = [s for s in sents if L.ADVANCE.search(self._flat(s))]
                neg = [s for s in adv if re.search(r"(?:aucune|pas\s+d'|n'est\s+pas\s+(?:pr[ée]vu|vers[ée]|accord[ée])\s+d')\s*avance", self._flat(s), re.I)]
                if adv and not neg:
                    c = self._base("ADVANCE_PAYMENT", adv, 0.8)
                    for s in adv:
                        t = self._flat(s)
                        for m in L.PCT_RE.finditer(t):
                            role, sub = self.classify_percentage(t, m, title)
                            c.percentages.append(Percentage(value=float(m.group(1).replace(",", ".")), role=role, subrole=sub, raw=m.group(0)))
                        for m in L.MONEY_RE.finditer(t):
                            c.amounts.append(Amount(value=L.parse_money(m.group(1)), unit=f"EUR {m.group(2) or ''}".strip(),
                                                    role=self.classify_amount(t, m), raw=m.group(0)))
                    cond = [s for s in sents if re.search(r"conditionn|garantie\s+à\s+premi[eè]re\s+demande|sauf\s+renoncement", self._flat(s), re.I)]
                    if cond:
                        c.attributes["conditions"] = [self._flat(x)[:200] for x in cond]
                        c.evidence += self._ev(*[x for x in cond if x not in adv[:3]])
                    clauses.append(c)
            # réexamen
            if L.REEXAM.search(title):
                req = [s for s in sents if L.PERMISSION.search(self._flat(s)) and L.SUPPLIER.search(self._flat(s)) and L.REQUEST.search(self._flat(s))]
                share = [s for s in sents if re.search(r"pris\w*\s+en\s+charge", self._flat(s), re.I) and L.PCT_RE.search(self._flat(s))]
                resp = [s for s in sents if self.parse_deadlines(self._flat(s)) and L.BUYER.search(self._flat(s))]
                ev = (req[:1] + share[:1] + resp[:1]) or sents[:1]
                c = self._base("REEXAMINATION_RIGHT", ev, 0.75)
                for s in share[:1]:
                    t = self._flat(s)
                    for m in L.PCT_RE.finditer(t):
                        c.percentages.append(Percentage(value=float(m.group(1).replace(",", ".")), role="OTHER", subrole="COST_SHARE", raw=m.group(0)))
                if resp:
                    c.deadline_rule = self.parse_deadlines(self._flat(resp[0]))[0]
                c.actor = "SUPPLIER" if req else "UNKNOWN"
                c.actor_basis = "EXPLICIT" if req else "NONE"
                if any(re.search(r"seule\s+volont[ée]\s+de\s+l'acheteur|à\s+l'initiative\s+du\s+pouvoir", self._flat(s), re.I) for s in sents):
                    c.attributes["buyer_discretion"] = True
                    c.review_reasons.append("Mise en œuvre à la discrétion de l'acheteur : droit non garanti.")
                clauses.append(c)
            # retenue de garantie
            ret = [s for s in sents if L.RETENTION.search(self._flat(s))]
            if ret and not any(re.search(r"(?:pas\s+de|aucune|n'est\s+pas\s+pr[ée]vu\w*\s+de)\s+retenue", self._flat(s), re.I) for s in ret):
                c = self._base("RETENTION_RELEASE", ret[:3], 0.75)
                for s in ret:
                    t = self._flat(s)
                    for m in L.PCT_RE.finditer(t):
                        c.percentages.append(Percentage(value=float(m.group(1).replace(",", ".")), role="OTHER", subrole="RETENTION_RATE", raw=m.group(0)))
                clauses.append(c)
            fb = [s for s in sents if L.FINAL_BALANCE.search(self._flat(s)) and re.search(r"d[ée]compte|solde\s+du\s+march|projet", self._flat(s), re.I)]
            if fb:
                clauses.append(self._base("FINAL_BALANCE", fb[:1], 0.7))
            # pénalités : exposition (non critique)
            if L.PENALTY.search(title):
                rates = []
                for s in sents:
                    t = self._flat(s)
                    for m in L.MONEY_RE.finditer(t):
                        role = self.classify_amount(t, m)
                        if role in ("PENALTY_RATE", "PENALTY_EXEMPTION_THRESHOLD"):
                            rates.append((s, Amount(value=L.parse_money(m.group(1)), unit=f"EUR {m.group(2) or ''}".strip(), role=role, raw=m.group(0))))
                if rates:
                    c = self._base("PENALTY_EXPOSURE", sorted({x[0].idx: x[0] for x in rates}.values(), key=lambda z: z.idx)[:6], 0.75)
                    c.amounts = [a for _, a in rates]
                    clauses.append(c)
        return clauses

    # ------------------------------------------------------------------ faits du contrat (dates, durée)
    def contract_terms(self) -> list[Clause]:
        out = []
        for s in self.sents:
            t = self._flat(s)
            if not re.search(r"\b(?:dur[ée]e|p[ée]riode\s+initiale|conclu|prend\s+effet|à\s+compter\s+d)", t, re.IGNORECASE):
                continue
            dm = list(L.DATE_RE.finditer(t))
            notif = re.search(r"notification", t, re.IGNORECASE)
            later = re.search(r"ult[ée]rieure|post[ée]rieure|plus\s+tardive", t, re.IGNORECASE)
            start_kw = re.search(r"à\s+compter\s+du|à\s+partir\s+du|prend\s+effet\s+le", t, re.IGNORECASE)
            if start_kw and dm and re.search(r"conclu|dur[ée]e|p[ée]riode|effet", t, re.IGNORECASE):
                d0 = L.parse_date(dm[0])
                c = self._base("CONTRACT_START", [s], 0.85)
                if notif and later:
                    c.date_expression = f"max({d0.isoformat()}, notification_date)"
                    c.missing_information = ["notification_date"]
                elif notif:
                    c.date_expression = f"one_of({d0.isoformat()}, notification_date)"
                    c.missing_information = ["notification_date"]
                    c.review_reasons.append("Deux dates possibles sans règle de choix explicite.")
                else:
                    c.date_expression = d0.isoformat()
                out.append(c)
            elif re.search(r"à\s+compter\s+de\s+(?:sa|la)\s+(?:date\s+de\s+)?notification", t, re.IGNORECASE) and re.search(r"conclu|dur[ée]e|p[ée]riode", t, re.IGNORECASE):
                c = self._base("CONTRACT_START", [s], 0.8)
                c.date_expression = "notification_date"
                c.missing_information = ["notification_date"]
                out.append(c)
            # durée
            init = re.search(r"(?:p[ée]riode\s+initiale|dur[ée]e(?:\s+initiale)?|conclu\w*\s+pour\s+une\s+(?:dur[ée]e|p[ée]riode))[^.;]{0,30}?\bd[e'u]\s*(" + L.NUM_WORD + r")\s*(ans?|ann[ée]es?|mois)\b", t, re.IGNORECASE)
            if init:
                months = L.to_int(init.group(1)) * (12 if L.unit_norm(init.group(2)) == "years" else 1)
                c = self._base("CONTRACT_DURATION", [s], 0.85)
                c.attributes["initial_months"] = months
                ren = []
                for s2 in [s] + [x for x in self.sents[s.idx + 1:s.idx + 4] if x.section == s.section]:
                    t2 = self._flat(s2)
                    for m in re.finditer(r"(" + L.NUM_WORD + r"|une\s+(?:premi|deuxi|second|troisi|quatri|cinqui)\w*)\s+fois\s+pour\s+une\s+(m[êe]me\s+p[ée]riode|p[ée]riode\s+d[e']\s*(" + L.NUM_WORD + r")\s*(ans?|ann[ée]es?|mois))", t2, re.IGNORECASE):
                        times_txt = m.group(1).lower()
                        times = 1 if times_txt.startswith("une ") else (L.to_int(times_txt) or 0)
                        if m.group(3):
                            per = L.to_int(m.group(3)) * (12 if L.unit_norm(m.group(4)) == "years" else 1)
                        else:
                            per = months
                        ren.append({"times": times, "period_months": per, "text": squash(m.group(0))})
                        if s2 is not s and s2 not in [x for x in []]:
                            c.evidence += [e for e in self._ev(s2) if e.quote not in [x.quote for x in c.evidence]]
                    rc = re.search(r"reconductible\w*\s+(?:tacitement\s+|expressément\s+)?(" + L.NUM_WORD + r")\s+fois", t2, re.IGNORECASE)
                    if rc and not ren:
                        ren.append({"times": L.to_int(rc.group(1)), "period_months": months, "text": squash(rc.group(0))})
                    mx = re.search(r"(?:dur[ée]e\s+totale|ne\s+(?:puisse|pourra|peut)\s+exc[ée]der)[^.;]{0,60}?(" + L.NUM_WORD + r")\s*(ans?|ann[ée]es?|mois)", t2, re.IGNORECASE)
                    if mx:
                        c.attributes["stated_max_months"] = L.to_int(mx.group(1)) * (12 if L.unit_norm(mx.group(2)) == "years" else 1)
                    ends = [L.parse_date(d) for d in L.DATE_RE.finditer(t2)]
                    ends = [d for d in ends if d]
                    if ends and re.search(r"\bau\s+\d", t2):
                        c.attributes["stated_last_date"] = max(ends).isoformat()
                c.attributes["renewals"] = ren
                c.attributes["max_months"] = months + sum(r["times"] * r["period_months"] for r in ren)
                out.append(c)
        # valeur du marché : seul un montant dont le rôle est ANNUAL_CONTRACT_VALUE est retenu
        for s in self.sents:
            t = self._flat(s)
            for m in L.MONEY_RE.finditer(t):
                if self.classify_amount(t, m) == "ANNUAL_CONTRACT_VALUE":
                    c = self._base("CONTRACT_VALUE", [s], 0.85)
                    c.amounts = [Amount(value=L.parse_money(m.group(1)), unit=f"EUR {m.group(2) or ''}".strip(),
                                        role="ANNUAL_CONTRACT_VALUE", raw=m.group(0))]
                    out.append(c)
        # durée maximale énoncée ailleurs (ex. « sans que la durée totale … excéder 4 ans »)
        for s in self.sents:
            t = self._flat(s)
            mx = re.search(r"dur[ée]e\s+totale[^.;]{0,60}?(?:exc[ée]der|d[ée]passer)\s+(" + L.NUM_WORD + r")\s*(ans?|ann[ée]es?|mois)", t, re.IGNORECASE)
            if mx:
                for c in out:
                    if c.event_type == "CONTRACT_DURATION" and "stated_max_months" not in c.attributes:
                        c.attributes["stated_max_months"] = L.to_int(mx.group(1)) * (12 if L.unit_norm(mx.group(2)) == "years" else 1)
                        c.evidence += self._ev(s)
        return out
