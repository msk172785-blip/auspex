"""Génère les documents FICTIFS de démonstration et du corpus d'évaluation synthétique.

Tous les documents portent la mention « EXEMPLE SIMULÉ » sur chaque page.
Acheteurs, titulaires, montants et identifiants d'indices sont inventés
(l'identifiant d'indice 999999999 est volontairement fictif).

Usage : python scripts/generate_demo_pdfs.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "simulated"
CORPUS = ROOT / "data" / "contracts"
GT = ROOT / "data" / "ground_truth"

BANNER = "EXEMPLE SIMULÉ — document fictif — aucune somme réelle n'est réclamée"
REF_DATE = "2026-10-03"  # date de référence figée pour des démonstrations reproductibles


def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm, BANNER)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(path: Path, pages: list[list[tuple[str, str]]]) -> None:
    """pages = [[(style, texte), ...], ...] ; style in {h1, h2, p, f}."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    styles = {"h1": ss["Title"], "h2": ss["Heading2"], "p": ss["BodyText"], "f": ss["Code"]}
    story = []
    for i, page in enumerate(pages):
        for st, txt in page:
            story.append(Paragraph(txt, styles[st]))
            story.append(Spacer(1, 4))
        if i < len(pages) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(str(path), pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                      title=path.stem, author="DÛ — exemple simulé").build(story, onFirstPage=_on_page, onLaterPages=_on_page)


def cover(num: str, objet: str, acheteur: str, kind: str = "Marché public de services") -> list[tuple[str, str]]:
    return [("h1", "CAHIER DES CLAUSES ADMINISTRATIVES PARTICULIÈRES (CCAP)"),
            ("p", kind),
            ("p", f"Marché n° {num}"),
            ("p", f"Objet du marché : {objet}"),
            ("p", f"Pouvoir adjudicateur : {acheteur}"),
            ("p", "Document fictif établi pour la démonstration du prototype DÛ.")]


GENERAL = [("h2", "Article 1 - Objet et durée"),
           ("p", "Le présent marché est conclu pour une durée de un (1) an à compter de sa date de notification. "
                 "Il est reconductible tacitement trois (3) fois par période de douze mois."),
           ("h2", "Article 2 - Pièces contractuelles"),
           ("p", "Les pièces contractuelles sont l'acte d'engagement, le présent CCAP, le CCTP et le bordereau des prix unitaires (BPU).")]

PAYMENT = [("h2", "Article 6 - Modalités de paiement"),
           ("p", "Le délai global de paiement est de 30 jours à compter de la réception de la facture."),
           ("p", "Le dépassement du délai de paiement ouvre droit, sans autre formalité, au versement d'intérêts moratoires "
                 "et d'une indemnité forfaitaire pour frais de recouvrement.")]


def ccap_case_a(path: Path):
    build_pdf(path, [
        cover("SIM-2026-A", "Nettoyage des locaux administratifs (exemple simulé)", "Collectivité Exemple A (fictive)"),
        GENERAL + [("h2", "Article 3 - Forme du marché"),
                   ("p", "Le marché est un marché ordinaire à prix global et forfaitaire."),
                   ("h2", "Article 4 - Prix"),
                   ("h2", "Article 4.1 - Forme des prix"),
                   ("p", "Les prix sont réputés comprendre toutes les charges fiscales, parafiscales ou autres."),
                   ("p", "Le montant annuel estimatif du marché est de 220 000 € HT.")],
        [("h2", "Article 4.3 - Révision des prix"),
         ("p", "Les prix du marché sont révisables annuellement à la date anniversaire du marché."),
         ("p", "La révision est effectuée par application de la formule suivante :"),
         ("f", "P = P0 x (0,15 + 0,85 x I/I0)"),
         ("p", "dans laquelle P0 est le prix initial du marché, I0 est la valeur de l'indice du coût horaire du travail "
               "révisé des activités de nettoyage (identifiant fictif 999999999) connue au mois zéro, et I la dernière valeur publiée à la date de révision."),
         ("p", "La révision n'est pas automatique. Le titulaire doit transmettre sa demande de révision, accompagnée du calcul "
               "et du nouveau bordereau des prix unitaires, au plus tard deux mois avant la date anniversaire du marché."),
         ("p", "À défaut de demande dans ce délai, le titulaire ne pourra plus se prévaloir de la révision pour la période considérée "
               "et les prix précédents restent applicables pendant douze mois.")],
        [("h2", "Article 5 - Retenue de garantie et avance"),
         ("p", "Il n'est pas prévu de retenue de garantie."),
         ("p", "Il n'est pas prévu d'avance.")] + PAYMENT,
    ])


def ccap_case_b(path: Path):
    build_pdf(path, [
        cover("SIM-2025-B", "Nettoyage de vitrerie (exemple simulé)", "Collectivité Exemple B (fictive)",
              "Accord-cadre de services"),
        GENERAL + [("h2", "Article 4 - Prix"),
                   ("p", "Les prix sont fermes pour toute la durée du marché."),
                   ("p", "Les prestations sont rémunérées par application des prix unitaires du bordereau des prix unitaires "
                         "aux quantités réellement exécutées.")] + PAYMENT,
    ])


def avenant_case_b(path: Path):
    build_pdf(path, [[
        ("h1", "AVENANT N° 1"),
        ("p", "Avenant n° 1 au marché n° SIM-2025-B - Nettoyage de vitrerie (exemple simulé)"),
        ("p", "Acheteur : Collectivité Exemple B (fictive)"),
        ("h2", "Article 1 - Modification du prix unitaire"),
        ("p", "Le prix unitaire du poste B-12 nettoyage de vitrerie au mètre carré est porté de 31,40 € HT à 33,10 € HT à compter du 1er mars 2026."),
        ("h2", "Article 2 - Autres clauses"),
        ("p", "Toutes les autres clauses du marché demeurent inchangées."),
    ]])


def ccap_case_c(path: Path):
    build_pdf(path, [
        cover("SIM-2026-C", "Entretien et remise en état de locaux (exemple simulé)", "Collectivité Exemple C (fictive)",
              "Accord-cadre à bons de commande"),
        GENERAL + [("h2", "Article 3 - Forme du marché"),
                   ("p", "Le marché est un accord-cadre exécuté au moyen de bons de commande, sans minimum, avec un maximum annuel de 60 000 € HT."),
                   ("p", "Des prestations exceptionnelles peuvent être commandées par bon de commande et sont facturées au bordereau des prix unitaires."),
                   ("h2", "Article 4 - Prix"),
                   ("p", "Les prix sont fermes.")] + PAYMENT,
    ])


def ccap_case_d(path: Path):
    build_pdf(path, [
        cover("SIM-2024-D", "Fourniture et pose de mobilier (exemple simulé)", "Collectivité Exemple D (fictive)",
              "Marché public de fournitures"),
        GENERAL + [("h2", "Article 4 - Prix"),
                   ("p", "Les prix sont fermes.")],
        [("h2", "Article 5 - Retenue de garantie"),
         ("p", "Une retenue de garantie de 5 % est appliquée sur le montant de chaque acompte."),
         ("p", "Le délai de garantie est fixé à 12 mois à compter de la date de réception."),
         ("p", "La retenue de garantie est remboursée un mois après l'expiration du délai de garantie."),
         ("p", "Le titulaire présente le projet de décompte final dans un délai de 45 jours suivant la réception.")] + PAYMENT,
    ])


def ccap_variant_firm(path: Path):
    build_pdf(path, [
        cover("SIM-2026-E", "Maintenance des extincteurs (variante de corpus simulée)", "Collectivité Exemple E (fictive)"),
        GENERAL + [("h2", "Article 4 - Prix"),
                   ("p", "Les prix du marché sont fermes et ne sont pas révisables."),
                   ("p", "Le marché est exécuté par émission de bons de commande.")] + PAYMENT,
    ])


def ccap_variant_auto(path: Path):
    build_pdf(path, [
        cover("SIM-2026-F", "Assistance informatique (variante de corpus simulée)", "Collectivité Exemple F (fictive)"),
        GENERAL,
        [("h2", "Article 7 - Variation des prix"),
         ("p", "Les prix sont révisables. Ils sont révisés automatiquement une fois par an, à la date anniversaire du marché, selon la formule :"),
         ("f", "Cn = 0,125 + 0,875 x (S/S0)"),
         ("p", "où S est la valeur de l'indice Syntec (identifiant fictif 999999998) du mois de révision et S0 sa valeur au mois zéro."),
         ("p", "La révision ne sera appliquée que si la variation de l'indice est supérieure à 1 % sur la période.")] + PAYMENT,
    ])


def ccap_variant_after(path: Path):
    build_pdf(path, [
        cover("SIM-2026-G", "Restauration collective (variante de corpus simulée)", "Collectivité Exemple G (fictive)"),
        GENERAL + [("h2", "Article 4 - Prix"),
                   ("p", "Les prix sont révisables selon les modalités de l'article 5.")],
        [("h2", "Article 5 - Modalités de révision"),
         ("f", "P = P0 x (0,15 + 0,50 x A/A0 + 0,35 x B/B0)"),
         ("p", "A est l'indice des prix à la production des produits alimentaires (identifiant fictif 999999997) et B l'indice du coût horaire du travail (identifiant fictif 999999996)."),
         ("p", "La demande de révision est adressée par le titulaire dans un délai de 30 jours à compter de la date anniversaire."),
         ("p", "Passé ce délai, le titulaire est réputé avoir renoncé à la révision pour l'année en cours."),
         ("p", "Une retenue de garantie de 5 % est appliquée.")] + PAYMENT,
    ])


def ccap_variant_offvocab(path: Path):
    """Rédaction volontairement hors du vocabulaire couvert par les règles (« ajustement » au lieu de « révision »).
    Sert à mesurer honnêtement les faux négatifs ; les règles ne doivent PAS être ajustées sur ce document."""
    build_pdf(path, [
        cover("SIM-2026-H", "Gardiennage (variante de corpus simulée, vocabulaire atypique)", "Collectivité Exemple H (fictive)"),
        GENERAL + [("h2", "Article 4 - Conditions financières"),
                   ("p", "Les tarifs font l'objet d'un ajustement annuel indexé sur l'évolution de l'indice du coût horaire du travail."),
                   ("p", "Toute demande d'ajustement tarifaire devra être notifiée à l'acheteur soixante jours au moins avant l'échéance annuelle ; "
                         "à défaut, l'ajustement est réputé abandonné pour l'exercice.")] + PAYMENT,
    ])


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    sim_flag = {"SIMULATED_EXAMPLE": True, "reference_date": REF_DATE}

    # --- CAS A : révision + forclusion
    a = SIM / "case_A"
    ccap_case_a(a / "CCAP_SIM_A_nettoyage.pdf")
    write_json(a / "meta.json", {**sim_flag, "title": "CAS A — Révision tarifaire à demander (nettoyage)",
                                 "user_inputs": {"supplier": "Société Exemple Propreté (fictive)", "annual_amount": 220000,
                                                 "contract_start_date": "2026-01-15", "revision_coefficient": 1.03}})
    # --- CAS B : avenant non appliqué
    b = SIM / "case_B"
    ccap_case_b(b / "CCAP_SIM_B_vitrerie.pdf")
    avenant_case_b(b / "AVENANT_1_SIM_B.pdf")
    write_json(b / "meta.json", {**sim_flag, "title": "CAS B — Avenant non appliqué à la facturation",
                                 "user_inputs": {"supplier": "Société Exemple Vitrerie (fictive)", "contract_start_date": "2025-09-01"}})
    write_json(b / "invoices.json", {"SIMULATED_EXAMPLE": True, "invoices": [
        {"invoice_id": "F-SIM-B-0201", "date": "2026-02-15", "lines": [{"item_code": "B-12", "label": "Vitrerie m²", "unit_price": 31.40, "quantity": 300}]},
        {"invoice_id": "F-SIM-B-0331", "date": "2026-03-31", "lines": [{"item_code": "B-12", "label": "Vitrerie m²", "unit_price": 31.40, "quantity": 400}]},
        {"invoice_id": "F-SIM-B-0430", "date": "2026-04-30", "lines": [{"item_code": "B-12", "label": "Vitrerie m²", "unit_price": 31.40, "quantity": 600}]},
    ]})
    # --- CAS C : bon de commande non facturé
    c = SIM / "case_C"
    ccap_case_c(c / "CCAP_SIM_C_bons_de_commande.pdf")
    write_json(c / "meta.json", {**sim_flag, "title": "CAS C — Bon de commande réalisé non facturé",
                                 "user_inputs": {"supplier": "Société Exemple Services (fictive)", "contract_start_date": "2026-01-01"}})
    write_json(c / "purchase_orders.json", {"SIMULATED_EXAMPLE": True, "purchase_orders": [
        {"po_id": "BC-SIM-2026-010", "date": "2026-03-02", "label": "Nettoyage après manifestation", "amount": 2100.00, "status": "REALISEE"},
        {"po_id": "BC-SIM-2026-014", "date": "2026-05-12", "label": "Prestation exceptionnelle de remise en état après travaux", "amount": 4800.00, "status": "REALISEE"},
        {"po_id": "BC-SIM-2026-019", "date": "2026-09-20", "label": "Prestation programmée", "amount": 1500.00, "status": "EN_COURS"},
    ]})
    write_json(c / "invoices.json", {"SIMULATED_EXAMPLE": True, "invoices": [
        {"invoice_id": "F-SIM-C-0315", "date": "2026-03-15", "lines": [{"po_ref": "BC-SIM-2026-010", "label": "Nettoyage après manifestation", "unit_price": 2100.00, "quantity": 1, "amount": 2100.00}]},
    ]})
    # --- CAS D : retenue de garantie non libérée
    d = SIM / "case_D"
    ccap_case_d(d / "CCAP_SIM_D_mobilier.pdf")
    write_json(d / "meta.json", {**sim_flag, "title": "CAS D — Retenue de garantie non restituée",
                                 "user_inputs": {"supplier": "Société Exemple Mobilier (fictive)", "contract_start_date": "2024-09-01"}})
    write_json(d / "retention.json", {"SIMULATED_EXAMPLE": True, "reception_date": "2025-06-30",
                                      "retained": [{"invoice_id": "F-SIM-D-01", "amount": 5000.00},
                                                   {"invoice_id": "F-SIM-D-02", "amount": 4500.00},
                                                   {"invoice_id": "F-SIM-D-03", "amount": 3000.00}],
                                      "payments": [{"label": "Règlement acompte 3", "amount": 57000.00, "date": "2025-08-10", "type": "INVOICE_PAYMENT"}]})

    # --- corpus d'évaluation synthétique : copie des cas + 3 variantes
    if CORPUS.exists():
        for p in CORPUS.glob("sim_*"):
            shutil.rmtree(p)
    for i, case in enumerate(["case_A", "case_B", "case_C", "case_D"], start=1):
        dst = CORPUS / f"sim_{i:03d}"
        shutil.copytree(SIM / case, dst)
    ccap_variant_firm(CORPUS / "sim_005" / "CCAP_SIM_E.pdf")
    ccap_variant_auto(CORPUS / "sim_006" / "CCAP_SIM_F.pdf")
    ccap_variant_after(CORPUS / "sim_007" / "CCAP_SIM_G.pdf")
    ccap_variant_offvocab(CORPUS / "sim_008" / "CCAP_SIM_H.pdf")
    for k in ("sim_005", "sim_006", "sim_007", "sim_008"):
        write_json(CORPUS / k / "meta.json", {**sim_flag, "user_inputs": {}})
    print("Documents simulés générés dans", SIM, "et", CORPUS)


if __name__ == "__main__":
    sys.exit(main())
