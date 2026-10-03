"""Calculs déterministes de DÛ.

Règle : aucun calcul financier ou de date n'est délégué à un modèle de langage.
Chaque fonction retourne une valeur ET la liste des étapes lisibles (`steps`),
affichées telles quelles dans l'interface (page Preuves).
Les montants utilisent Decimal, arrondis au centime (ROUND_HALF_UP).
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

CENT = Decimal("0.01")


def D(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        return Decimal(repr(x))
    return Decimal(str(x).replace(" ", "").replace(" ", "").replace(",", "."))


def money(x: Decimal) -> Decimal:
    return D(x).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_eur(x) -> str:
    q = money(D(x))
    sign = "-" if q < 0 else ""
    q = abs(q)
    ent, dec = f"{q:.2f}".split(".")
    ent = f"{int(ent):,}".replace(",", " ")
    return f"{sign}{ent},{dec} €" if dec != "00" else f"{sign}{ent} €"


def fmt_date(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else "inconnue"


@dataclass
class CalcResult:
    value: object
    steps: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.value is not None and not self.missing_information

    def to_dict(self) -> dict:
        v = self.value
        if isinstance(v, Decimal):
            v = float(v)
        elif isinstance(v, date):
            v = v.isoformat()
        elif isinstance(v, dict):
            v = {k: (float(x) if isinstance(x, Decimal) else x.isoformat() if isinstance(x, date) else x)
                 for k, x in v.items()}
        return {"value": v, "steps": self.steps, "missing_information": self.missing_information}


# ---------------------------------------------------------------- dates

def add_months(d: date, months: int) -> date:
    """Ajoute (ou retranche) des mois calendaires ; le jour est borné à la fin du mois."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def add_days(d: date, days: int) -> date:
    return date.fromordinal(d.toordinal() + days)


def next_anniversary(start: date, reference: date, end: Optional[date] = None) -> CalcResult:
    """Prochaine date anniversaire de `start` strictement postérieure à `reference`."""
    steps = [f"Date de départ du contrat : {fmt_date(start)}",
             f"Date de référence (aujourd'hui ou date choisie) : {fmt_date(reference)}"]
    n = 1
    while True:
        ann = add_months(start, 12 * n)
        if ann > reference:
            break
        n += 1
    steps.append(f"Anniversaire n°{n} = {fmt_date(start)} + {n} an(s) = {fmt_date(ann)}")
    if end and ann > end:
        steps.append(f"Cette date dépasse la fin du contrat ({fmt_date(end)}) : plus d'anniversaire à venir.")
        return CalcResult(None, steps, ["aucun anniversaire avant la fin du contrat"])
    return CalcResult(ann, steps)


def apply_deadline_rule(rule: dict, reference_date: Optional[date], reference_label: str) -> CalcResult:
    """rule = {"amount": 2, "unit": "months"|"days", "direction": "before"|"after", "reference": "..."}"""
    if not rule:
        return CalcResult(None, ["Aucune règle de délai."], ["deadline_rule"])
    amount, unit, direction = rule.get("amount"), rule.get("unit"), rule.get("direction")
    if reference_date is None:
        return CalcResult(None, [f"Règle contractuelle : {rule.get('text', '')}",
                                 f"Date de référence ({reference_label}) inconnue : échéance non calculable."],
                          [reference_label])
    if amount is None or unit not in ("months", "days") or direction not in ("before", "after"):
        return CalcResult(None, [f"Règle non interprétable automatiquement : {rule}"], ["deadline_rule"])
    sign = -1 if direction == "before" else 1
    if unit == "months":
        res = add_months(reference_date, sign * amount)
        unit_fr = "mois"
    else:
        res = add_days(reference_date, sign * amount)
        unit_fr = "jour(s) calendaire(s)"
    op = "−" if sign < 0 else "+"
    steps = [f"Règle contractuelle : {amount} {unit_fr} {'avant' if sign < 0 else 'après'} {reference_label}",
             f"{reference_label} = {fmt_date(reference_date)}",
             f"Échéance = {fmt_date(reference_date)} {op} {amount} {unit_fr} = {fmt_date(res)}"]
    return CalcResult(res, steps)


def contract_end(start: date, duration_months: int) -> CalcResult:
    end = add_days(add_months(start, duration_months), -1)
    return CalcResult(end, [f"Fin = {fmt_date(start)} + {duration_months} mois − 1 jour = {fmt_date(end)}"])


# ---------------------------------------------------------------- révision

_FORMULA_PARAM_RE = re.compile(
    r"\(\s*(?P<a>\d+(?:[.,]\d+)?)\s*\+\s*(?P<b>\d+(?:[.,]\d+)?)\s*[x×*.]?\s*\(?\s*(?P<num>[A-Za-z][\w]*)\s*/\s*(?P<den>[A-Za-z][\w]*)\s*\)?\s*\)"
)


_FORMULA_COEF_RE = re.compile(
    r"=\s*(?P<a>\d+(?:[.,]\d+)?)\s*\+\s*(?P<b>\d+(?:[.,]\d+)?)\s*[x×*]\s*\(?\s*(?P<num>[A-Za-z]\w*)\s*/\s*(?P<den>[A-Za-z]\w*)\s*\)?\s*$"
)


def parse_parametric_formula(formula: str) -> Optional[dict]:
    """Reconnaît la forme P = P0 × (a + b × In/I0). Retourne None sinon (pas de devinette).

    Ne gère qu'UN indice. Les formules multi-indices renvoient None -> saisie manuelle du coefficient.
    """
    if not formula:
        return None
    f = formula.replace("×", "x")
    matches = list(_FORMULA_PARAM_RE.finditer(f))
    if not matches:
        # forme « coefficient » : Cn = a + b × (In/I0)
        m = _FORMULA_COEF_RE.search(f.strip())
        if m:
            a, b = D(m.group("a")), D(m.group("b"))
            return {"fixed_part": a, "variable_part": b, "index_term": f"{m.group('num')}/{m.group('den')}",
                    "weights_sum": a + b}
        return None
    if len(matches) != 1:
        return None
    # refuser les formules à plusieurs termes indiciels : "(0,15 + 0,45 x I1/I10 + 0,40 x I2/I20)"
    inner = f[matches[0].start():]
    if inner.count("/") > 1 and re.search(r"/\s*[A-Za-z]\w*\s*\+", inner):
        return None
    m = matches[0]
    a, b = D(m.group("a")), D(m.group("b"))
    return {"fixed_part": a, "variable_part": b, "index_term": f"{m.group('num')}/{m.group('den')}",
            "weights_sum": a + b}


def revision_coefficient(formula: Optional[str], index_base: Optional[float], index_new: Optional[float],
                         coefficient_override: Optional[float] = None) -> CalcResult:
    if coefficient_override is not None:
        c = D(coefficient_override)
        return CalcResult(c, [f"Coefficient de révision saisi par l'utilisateur : {c} (non recalculé par DÛ)"])
    parsed = parse_parametric_formula(formula or "")
    missing = []
    if parsed is None:
        missing.append("formule de révision interprétable (ou coefficient saisi manuellement)")
    if index_base is None:
        missing.append("valeur de l'indice de base I0")
    if index_new is None:
        missing.append("valeur de l'indice de révision In")
    if missing:
        return CalcResult(None, ["Coefficient non calculable : données manquantes."], missing)
    a, b = parsed["fixed_part"], parsed["variable_part"]
    steps = [f"Formule reconnue : P = P0 × ({a} + {b} × {parsed['index_term']})"]
    if parsed["weights_sum"] != 1:
        steps.append(f"ATTENTION : a + b = {parsed['weights_sum']} ≠ 1 — formule à vérifier manuellement.")
    i0, i1 = D(index_base), D(index_new)
    ratio = i1 / i0
    c = (a + b * ratio)
    c4 = c.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    steps += [f"Rapport d'indices = {i1} / {i0} = {ratio.quantize(Decimal('0.000001'))}",
              f"Coefficient = {a} + {b} × {ratio.quantize(Decimal('0.000001'))} = {c4} (arrondi à 4 décimales)"]
    res = CalcResult(c4, steps)
    if parsed["weights_sum"] != 1:
        res.missing_information.append("vérification humaine de la formule (pondérations ≠ 1)")
    return res


def revision_delta(old_annual_price, coefficient, threshold_pct: Optional[float] = None,
                   cap_pct: Optional[float] = None) -> CalcResult:
    """old × coef ; applique éventuellement un seuil de déclenchement et un plafond (en %)."""
    old = D(old_annual_price)
    c = D(coefficient)
    steps = [f"Prix annuel actuel = {fmt_eur(old)}", f"Coefficient de révision = {c}"]
    variation_pct = ((c - 1) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    steps.append(f"Variation = ({c} − 1) × 100 = {variation_pct} %")
    applied = c
    if threshold_pct is not None:
        t = D(threshold_pct)
        if abs(variation_pct) < t:
            steps.append(f"Seuil contractuel de déclenchement : {t} % — variation inférieure : pas de révision.")
            return CalcResult({"old_annual_price": money(old), "coefficient": c, "new_annual_price": money(old),
                               "potential_delta": Decimal("0.00"), "variation_pct": variation_pct,
                               "threshold_blocked": True}, steps)
        steps.append(f"Seuil contractuel de déclenchement : {t} % — atteint.")
    if cap_pct is not None:
        cap = D(cap_pct)
        if variation_pct > cap:
            applied = 1 + cap / 100
            steps.append(f"Plafond contractuel {cap} % : coefficient ramené à {applied}.")
    new = money(old * applied)
    delta = money(new - old)
    steps += [f"Nouveau prix annuel = {fmt_eur(old)} × {applied} = {fmt_eur(new)}",
              f"Écart potentiel = {fmt_eur(new)} − {fmt_eur(old)} = {fmt_eur(delta)} / an"]
    return CalcResult({"old_annual_price": money(old), "coefficient": c, "new_annual_price": new,
                       "potential_delta": delta, "variation_pct": variation_pct,
                       "threshold_blocked": False}, steps)


# ---------------------------------------------------------------- rapprochements (P2)

def amendment_underbilling(old_unit_price, new_unit_price, quantity_billed_at_old) -> CalcResult:
    o, n, q = D(old_unit_price), D(new_unit_price), D(quantity_billed_at_old)
    gap = money((n - o) * q)
    return CalcResult(gap, [
        f"Prix unitaire avant avenant = {fmt_eur(o)} ; après avenant = {fmt_eur(n)}",
        f"Écart unitaire = {fmt_eur(n)} − {fmt_eur(o)} = {fmt_eur(n - o)}",
        f"Quantité facturée à l'ancien prix après la date d'effet = {q}",
        f"Écart = {fmt_eur(n - o)} × {q} = {fmt_eur(gap)}",
    ])


def unbilled_amount(expected_amount, billed_amount) -> CalcResult:
    e, b = D(expected_amount), D(billed_amount)
    gap = money(e - b)
    return CalcResult(gap, [f"Montant attendu = {fmt_eur(e)}", f"Montant retrouvé dans les factures = {fmt_eur(b)}",
                            f"Écart potentiel = {fmt_eur(e)} − {fmt_eur(b)} = {fmt_eur(gap)}"])


def to_decimal_or_none(x) -> Optional[Decimal]:
    if x is None or x == "":
        return None
    try:
        return D(x)
    except (InvalidOperation, ValueError):
        return None
