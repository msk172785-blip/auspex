from du_engine.v1.document import build
from du_engine.v1.verify import Verifier
from du_engine.v1.schema import Clause, Evidence, Percentage

from test_v1_adversarial import doc_from

FOOT = "Cahier des clauses particulières – marché test\nPage {n} sur 3"


def three_pages():
    return doc_from(
        "ARTICLE 4 : PRIX\n\n4.1 - Forme des prix\nLes prix sont fermes la première année.\n\n4.3 - Révision des prix\nLes prix sont révisés selon l'article R. 2112-13 du Code. La demande est adressée à l'acheteur.\n" + FOOT.format(n=1),
        "Elle mentionne le coefficient retenu.\n\n4.2.6. – Contenu des prix\nLes prix comprennent toutes charges.\n" + FOOT.format(n=2),
        "ARTICLE 5 - PAIEMENT\nLe délai de paiement est de 30 jours, conformément à l'article 4.9.\n" + FOOT.format(n=3),
    )


def test_dash_title_is_article_and_text_not_attached_to_previous():
    sd = build(three_pages())
    nums = [s.number for s in sd.sections]
    assert "4.3" in nums and "4.2.6" in nums and "4.1" in nums
    s43 = next(s for s in sd.sections if s.number == "4.3")
    assert s43.title == "Révision des prix"
    sent = next(x for x in sd.sentences if "demande est adressée" in x.text)
    assert sd.section(sent.section).number == "4.3"
    cont = next(x for x in sd.sentences if "coefficient retenu" in x.text)       # suite de 4.3 sur la page 2
    assert sd.section(cont.section).number == "4.3" and cont.page == 2


def test_boilerplate_removed_and_abbreviation_not_split():
    sd = build(three_pages())
    assert "Page 1 sur 3" not in sd.clean_text and "marché test" not in sd.clean_text
    assert any("R. 2112-13 du Code" in x.text for x in sd.sentences)


def test_anomalies_reported_not_corrected():
    sd = build(three_pages())
    a = " ".join(sd.anomalies)
    assert "4.3 (p.1) puis 4.2.6" in a or "Ordre non monotone" in a
    assert "4.9" in a


def test_verifier_rejects_unknown_quote_and_corrects_page():
    sd = build(three_pages())
    v = Verifier(sd)
    ok = Clause(event_type="PAYMENT_TERM", evidence=[Evidence(document="x", page=1, page_end=None, article="9",
                                                              quote="Le délai de paiement est de 30 jours")])
    v.verify(ok)
    assert ok.status != "REJECTED_UNSUPPORTED" and ok.evidence[0].page == 3 and ok.source_article == "5"
    assert any("page corrigée" in c for c in ok.checks)
    bad = Clause(event_type="PAYMENT_TERM", evidence=[Evidence(document="x", page=3, page_end=None, article="5",
                                                               quote="Le délai de paiement est de 45 jours")])
    v.verify(bad)
    assert bad.status == "REJECTED_UNSUPPORTED"
    num = Clause(event_type="PRICE_REVISION_THRESHOLD", percentages=[Percentage(30.0, "CAP", "CAP_ANNUAL")],
                 evidence=[Evidence(document="x", page=3, page_end=None, article="5", quote="Le délai de paiement est de 30 jours")])
    v.verify(num)
    assert num.status == "REJECTED_UNSUPPORTED"  # « 30 jours » n'ancre pas « 30 % »
