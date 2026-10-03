from du_engine.v1 import coherence
from du_engine.v1.schema import Amount, Clause, Evidence, Percentage


def C(etype, quote, **kw):
    c = Clause(event_type=etype, evidence=[Evidence("d", 1, 1, "1", quote)], status="AUTO_EXTRACTED", **kw)
    return c


def test_cap_and_threshold_same_value_conflict():
    c = C("PRICE_REVISION_THRESHOLD", "La variation est plafonnée à 3 % et ne sera appliquée que si elle dépasse 3 %.",
          percentages=[Percentage(3.0, "CAP", "CAP_ANNUAL"), Percentage(3.0, "THRESHOLD", "TRIGGER_THRESHOLD")])
    coherence.run([c])
    assert c.status == "REVIEW_REQUIRED"


def test_po_amount_cannot_be_contract_value():
    c = C("PURCHASE_ORDER_BILLING", "un montant annuel maximum de commandes arrêté à 12 000 € HT",
          amounts=[Amount(12000.0, "EUR HT", "ANNUAL_CONTRACT_VALUE")])
    coherence.run([c])
    assert c.amounts[0].role == "OTHER" and c.status == "REVIEW_REQUIRED"


def test_inaction_consequence_cannot_be_automatic_revision():
    q = "À défaut de demande, les prix sont reconduits d'office."
    pr = C("PRICE_REVISION", q, trigger="AUTOMATIC")
    k = C("CONSEQUENCE_IF_NO_ACTION", q, consequence_if_no_action={"type": "PRICE_KEPT", "polarity_for_supplier": "UNFAVORABLE"})
    coherence.run([pr, k])
    assert pr.trigger == "" and pr.status == "REVIEW_REQUIRED"


def test_operational_frequency_dropped():
    pr = C("PRICE_REVISION", "Le titulaire nettoie les conteneurs une fois par trimestre.", attributes={"revision_frequency": "QUARTERLY"})
    coherence.run([pr])
    assert "revision_frequency" not in pr.attributes


def test_conditional_date_never_absolute():
    c = C("CONTRACT_START", "à compter du 1er mars 2027 ou de sa notification si postérieure", date_expression="max(2027-03-01, notification_date)")
    coherence.run([c])
    assert c.status == "REVIEW_REQUIRED" and "notification_date" in c.missing_information
