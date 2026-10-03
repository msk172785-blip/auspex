"""Tests adversariaux du moteur v1 — textes INDÉPENDANTS (aucun n'est tiré de real_001 ni du corpus simulé).

Chaque test vise une capacité générale, pas une phrase : synonymes de « révision », voix passive,
conséquence répartie sur plusieurs phrases, rôles des nombres, date conditionnelle, négation, piège lexical.
"""
from __future__ import annotations

from datetime import date

from du_engine.models import DocumentText, PageText
from du_engine.pdf_reader import _article_marks, normalize_text
from du_engine.v1.engine import analyze_v1

REF = date(2026, 10, 3)


def doc_from(*pages: str, name: str = "ccap_test.pdf") -> DocumentText:
    out = []
    for i, t in enumerate(pages, start=1):
        txt = normalize_text(t)
        out.append(PageText(document=name, page=i, text=txt, article_marks=_article_marks(txt)))
    return DocumentText(name=name, pages=out, has_text_layer=True)


def run(*pages: str, **kw) -> dict:
    return analyze_v1([doc_from(*pages)], reference_date=REF, **kw)


def of(r: dict, etype: str) -> list[dict]:
    return [e for e in r["events"] if e["event_type"] == etype]


# 1. « ajustement tarifaire » au lieu de « révision » + délai + conséquence
def test_tariff_adjustment_without_word_revision():
    r = run("""ARTICLE 6 – ÉVOLUTION TARIFAIRE

Les tarifs unitaires sont ajustés une fois par an selon l'évolution de l'indice Syntec.
Le prestataire formule sa demande d'ajustement par écrit au plus tard trente jours avant la date anniversaire de la notification.
Faute de demande dans ce délai, les tarifs en vigueur demeurent applicables jusqu'à l'échéance suivante.
""")
    assert of(r, "PRICE_REVISION")
    dl = of(r, "PRICE_REVISION_DEADLINE")
    assert dl and dl[0]["deadline_rule"]["amount"] == 30 and dl[0]["deadline_rule"]["unit"] == "days"
    assert dl[0]["deadline_rule"]["direction"] == "before" and dl[0]["deadline_rule"]["anchor"] == "ANNIVERSARY"
    assert dl[0]["actor"] == "SUPPLIER"
    cons = of(r, "CONSEQUENCE_IF_NO_ACTION")
    assert cons and cons[0]["consequence_if_no_action"]["type"] == "PRICE_KEPT"
    assert cons[0]["consequence_if_no_action"]["polarity_for_supplier"] == "UNFAVORABLE"


# 2. plafond ET seuil dans la même clause
def test_cap_and_threshold_together():
    r = run("""ARTICLE 5 – VARIATION DES PRIX

Les prix sont révisés annuellement par application de l'indice ICHT-rev-TS.
La révision n'est mise en œuvre que si la variation de l'indice excède 2 % sur la période.
Elle est en tout état de cause plafonnée à 4 % par an.
""")
    pcts = {(p["value"], p["role"], p["subrole"]) for e in of(r, "PRICE_REVISION_THRESHOLD") for p in e["percentages"]}
    assert (2.0, "THRESHOLD", "TRIGGER_THRESHOLD") in pcts
    assert (4.0, "CAP", "CAP_ANNUAL") in pcts
    assert not any(p[0] == 2.0 and p[1] == "CAP" for p in pcts)
    assert not any(p[0] == 4.0 and p[1] == "THRESHOLD" for p in pcts)


# 3. plusieurs montants aux rôles différents
def test_amount_roles():
    r = run("""ARTICLE 3 – MONTANTS

Le montant annuel estimatif du marché est de 180 000 € HT.
Les prestations complémentaires sont commandées par bons de commande dans la limite d'un montant maximum annuel de 25 000 € HT.
Une avance de 5 % est versée pour toute commande d'un montant supérieur à 50 000 € HT.
""")
    roles = {(a["value"], a["role"]) for e in r["events"] for a in e["amounts"]}
    assert (25000.0, "PURCHASE_ORDER_ANNUAL_CEILING") in roles
    assert (50000.0, "ADVANCE_ELIGIBILITY_THRESHOLD") in roles
    assert r["contract"]["annual_contract_value"]["value"] == 180000.0
    assert not any(v == 25000.0 and role == "ANNUAL_CONTRACT_VALUE" for v, role in roles)
    adv = {(p["value"], p["subrole"]) for e in of(r, "ADVANCE_PAYMENT") for p in e["percentages"]}
    assert (5.0, "ADVANCE_RATE") in adv


# 4. date conditionnelle
def test_conditional_start_date_is_not_absolute():
    r = run("""ARTICLE 2 – DURÉE

Le marché prend effet à compter du 1er mars 2027 ou de sa notification si celle-ci est postérieure.
Il est conclu pour une durée de deux ans, reconductible une fois pour une période d'un an.
""")
    st = r["contract"]["start_date"]
    assert st["value"] is None
    assert st["expression"] == "max(2027-03-01, notification_date)"
    assert "notification_date" in st["missing"]
    assert r["contract"]["duration"]["max_months"] == 36


# 5. obligation à la voix passive, sans sujet
def test_passive_obligation_actor_inferred():
    r = run("""ARTICLE 7 – RÉVISION

Les prix sont révisables chaque année.
Les justificatifs de calcul et le nouveau bordereau des prix doivent être adressés au pouvoir adjudicateur au plus tard un mois avant chaque date anniversaire.
""")
    dl = of(r, "PRICE_REVISION_DEADLINE")
    assert dl and dl[0]["deadline_rule"]["amount"] == 1 and dl[0]["deadline_rule"]["unit"] == "months"
    assert dl[0]["actor"] == "SUPPLIER"
    assert dl[0]["actor_basis"] != "EXPLICIT"          # déduction signalée comme telle
    assert dl[0]["status"] != "AUTO_EXTRACTED"


# 6. conséquence répartie sur plusieurs phrases
def test_consequence_spread_over_sentences():
    r = run("""ARTICLE 8 – ACTUALISATION DES TARIFS

Le titulaire peut solliciter l'actualisation de ses tarifs.
Sa demande doit parvenir à l'acheteur deux mois avant le terme de chaque période annuelle.
Si ce délai n'est pas respecté, l'acheteur n'est pas tenu d'examiner la demande.
Les tarifs antérieurs continuent alors de s'appliquer.
""")
    cons = of(r, "CONSEQUENCE_IF_NO_ACTION")
    assert cons, "conséquence non détectée"
    c = cons[0]["consequence_if_no_action"]
    assert c["type"] == "PRICE_KEPT" and c["polarity_for_supplier"] == "UNFAVORABLE"
    quotes = " ".join(e["quote"] for e in cons[0]["evidence"])
    assert "continuent alors" in quotes and "Si ce délai" in quotes


# 7. aucun mot « révision » : indexation + délai à date fixe
def test_indexation_without_revision_word():
    r = run("""ARTICLE 4 – PRIX

Les prix unitaires sont indexés au 1er janvier de chaque année sur l'indice des prix à la consommation publié par l'INSEE.
Pour en bénéficier, le fournisseur transmet sa nouvelle grille tarifaire avant le 30 novembre.
""")
    assert of(r, "PRICE_REVISION")
    acts = of(r, "SUPPLIER_ACTION_REQUIRED") + of(r, "PRICE_REVISION_DEADLINE")
    assert acts and any(a["deadline_rule"] and a["deadline_rule"].get("anchor") == "FIXED_DAY" for a in acts)


# 8. « prévision » ne doit pas déclencher « révision » ; fréquence opérationnelle ≠ fréquence de révision
def test_prevision_is_not_revision():
    r = run("""ARTICLE 9 – DÉCHETS

Le titulaire sort les conteneurs en prévision de la collecte hebdomadaire.
Il nettoie les conteneurs une fois par trimestre et la facturation de cette prestation est comprise dans le prix forfaitaire.
""")
    assert not of(r, "PRICE_REVISION")
    assert not of(r, "PRICE_REVISION_DEADLINE")


# 9. négation : prix fermes et non révisables
def test_negated_revision_is_firm_price():
    r = run("""ARTICLE 4 – PRIX

Les prix du marché sont fermes et ne sont pas révisables pendant toute la durée du contrat.
""")
    assert not of(r, "PRICE_REVISION")


# 10. preuve inventée par un interpréteur : rejet obligatoire
def test_llm_invented_quote_is_rejected():
    import json
    from types import SimpleNamespace

    fake = {"clauses": [{
        "event_type": "PRICE_REVISION_DEADLINE", "actor": "SUPPLIER", "action_required": "demander",
        "trigger": "", "deadline_rule": {"amount": 3, "unit": "months", "direction": "before", "anchor": "ANNIVERSARY", "anchor_text": "anniversaire"},
        "deadline_basis": "ANNIVERSARY", "consequence_if_action": "", "consequence_if_no_action": {"type": "NONE", "polarity_for_supplier": "UNKNOWN", "inactive_party": "NONE", "text": ""},
        "amounts": [], "percentages": [], "quotes": ["La demande doit être adressée trois mois avant la date anniversaire du marché."],
        "uncertainty": "LOW", "notes": ""}, {
        "event_type": "PRICE_REVISION", "actor": "UNKNOWN", "action_required": "", "trigger": "",
        "deadline_rule": {"amount": None, "unit": "none", "direction": "none", "anchor": "NONE", "anchor_text": ""},
        "deadline_basis": "", "consequence_if_action": "", "consequence_if_no_action": {"type": "NONE", "polarity_for_supplier": "UNKNOWN", "inactive_party": "NONE", "text": ""},
        "amounts": [], "percentages": [{"value": 7.0, "role": "CAP", "subrole": "CAP_ANNUAL"}],
        "quotes": ["Les prix sont révisables chaque année."], "uncertainty": "LOW", "notes": ""}]}

    class FakeMessages:
        def create(self, **kw):
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(fake))])

    client = SimpleNamespace(messages=FakeMessages())
    r = run("""ARTICLE 7 – RÉVISION

Les prix sont révisables chaque année.
""", use_llm=True, llm_client=client)
    rej = r["rejected_unsupported"]
    # citation absente du document -> rejet
    assert any(e["event_type"] == "PRICE_REVISION_DEADLINE" and e["interpreter"] == "LLM" for e in rej)
    # citation réelle mais nombre (7 %) absent de la clause -> rejet
    assert any(e["event_type"] == "PRICE_REVISION" and e["interpreter"] == "LLM" for e in rej)
    assert not any(e["interpreter"] == "LLM" and e["event_type"] == "PRICE_REVISION_DEADLINE" for e in r["events"])
