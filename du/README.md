# DÛ — prototype v0 de Revenue Assurance pour fournisseurs de marchés publics

DÛ lit les PDF d'un marché public (CCAP, AE, CCP, avenants). Il en extrait les clauses financières importantes pour le titulaire et les transforme en événements économiques structurés. Chaque événement est sourcé : document, page, article et extrait exact.

Objectif de cette version : valider le moteur. Ce n'est pas un SaaS (pas de comptes, de paiement ni de multi-tenant).

## Principes appliqués dans le code

- Aucune clause n'est inventée. Une valeur n'est retenue que si une phrase du document la contient. L'extrait est stocké, puis recontrôlé littéralement dans le texte de la page (`quote_verified`).
- Les données sont séparées en trois natures : FACT (lu dans le contrat), CALCULATION (calcul Python déterministe, étapes affichées), USER_INPUT (saisi). Ce qui manque est listé dans `missing_information`.
- Statuts produits par le moteur :
  - `AUTO_EXTRACTED` : preuve vérifiée et confiance ≥ 0,80 ;
  - `REVIEW_REQUIRED` : incertitude, contradiction ou information manquante ;
  - `NOT_FOUND` : aucune mention trouvée, ce qui ne prouve pas l'absence de la clause.
- `VALIDATED` n'est jamais attribué automatiquement. Il faut un clic humain dans la page Preuves, enregistré dans `validations.json`.
- Aucun modèle de langage n'est utilisé dans cette version. L'extraction repose sur des règles explicites (regex sur le vocabulaire juridique français) et tous les calculs sont faits en Python (`Decimal`).
- Les exemples sont fictifs et marqués `SIMULATED_EXAMPLE = true`, avec le bandeau « Exemple simulé — aucune somme réelle n'est réclamée ».

## Installation (Python 3.10+)

```bash
cd du
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Commandes

| Action | Commande |
|---|---|
| (Re)générer les documents simulés et le corpus synthétique | `python scripts/generate_demo_pdfs.py` |
| Interface locale | `streamlit run app.py` puis http://localhost:8501 |
| Analyse d'un PDF en ligne de commande | `python analyze.py chemin/CCAP.pdf --start 2026-01-15 --amount 220000 --coef 1.03` |
| Analyse d'un dossier (PDF + JSON de rapprochement) | `python analyze.py data/simulated/case_A` |
| Évaluation sur la vérité terrain | `python run_evaluation.py` (contrats réels seulement : `--real-only`) |
| Tests | `python -m pytest -q` |

Les documents simulés sont déjà dans le dépôt. Le script de génération n'est utile que pour les recréer.

## Interface (Streamlit)

1. Analyser un marché : dépôt d'un ou plusieurs PDF. Saisies facultatives : nom du marché, acheteur, fournisseur, montant annuel, date de début, coefficient ou indices, JSON de factures, bons de commande et retenue. Les documents sont conservés dans `data/uploads/<id>/`.
2. Vue d'ensemble : acheteur, objet, durée, montant, type de prix, nombre d'événements, puis tableau de tous les champs (nature, statut, confiance, source, éléments manquants). Export JSON.
3. Alertes DÛ : une carte par événement (sévérité, deadline, impact, action, source, statut, éléments manquants) et un bouton « Voir la preuve ».
4. Preuves : extrait exact, page, document et texte complet de la page avec l'extrait surligné. Puis données extraites, étapes du calcul, hypothèses, informations manquantes, confiance, et validation ou rejet humain.

S'y ajoutent deux pages : Exemples simulés (cas A à D) et Évaluation.

## Les quatre scénarios simulés (`data/simulated/`)

Date de référence figée au 03/10/2026 pour que les résultats soient reproductibles.

| Cas | Documents | Résultat attendu et obtenu |
|---|---|---|
| A | CCAP fictif de nettoyage, article 4.3 page 3 ; montant 220 000 € et coefficient 1,03 saisis | Révision à demander, deadline 15/11/2026, impact +6 600 €/an, forclusion (prix précédents maintenus 12 mois) |
| B | CCAP + avenant n° 1 (31,40 € → 33,10 € HT au 01/03/2026) + factures JSON | 1 000 unités facturées à l'ancien prix après la date d'effet : écart de 1 700 € |
| C | CCAP à bons de commande + BC JSON + factures JSON | BC-SIM-2026-014 réalisé (4 800 €) sans ligne de facture : écart de 4 800 € |
| D | CCAP avec retenue de 5 %, garantie 12 mois, remboursement 1 mois après + JSON de retenue | Libération exigible le 30/07/2026, aucun remboursement trouvé : 12 500 € à vérifier |

## Corpus d'évaluation (préparé pour 50 contrats)

```
data/contracts/<contract_id>/      PDF du marché (+ meta.json, invoices.json… facultatifs)
data/contracts/<contract_id>.pdf   ou un PDF isolé
data/ground_truth/<contract_id>.json   vérité terrain manuelle (modèle : _TEMPLATE.json)
data/results/                      sorties d'analyse et d'évaluation (non versionnées)
```

Pour ajouter un vrai contrat :

1. Copier le PDF dans `data/contracts/contract_001/`.
2. Copier `data/ground_truth/_TEMPLATE.json` vers `data/ground_truth/contract_001.json`.
3. Le remplir à la main depuis le PDF (`null` = clause absente).
4. Passer `"validated": true` et `"SIMULATED_EXAMPLE": false`.
5. Lancer `python run_evaluation.py`.

`run_evaluation.py` affiche :

- le nombre de contrats ;
- les événements attendus et détectés ;
- les TP, FP et FN, en isolant les FN critiques (événements à échéance) ;
- le recall, un recall pondéré (échéances ×3) et la precision ;
- l'exactitude par champ (présence de révision, formule, indice, deadline, action fournisseur, forclusion, seuil, page/source) ;
- la liste exacte des erreurs.

Les fichiers de vérité terrain avec `validated: false` sont ignorés.

## Données de rapprochement (P2, JSON)

```json
// invoices.json
{"invoices": [{"invoice_id": "F-1", "date": "2026-03-31",
  "lines": [{"item_code": "B-12", "unit_price": 31.40, "quantity": 400, "po_ref": null, "amount": null}]}]}
// purchase_orders.json   (status : REALISEE | EN_COURS)
{"purchase_orders": [{"po_id": "BC-14", "date": "2026-05-12", "label": "…", "amount": 4800.0, "status": "REALISEE"}]}
// retention.json
{"reception_date": "2025-06-30", "retained": [{"invoice_id": "F-1", "amount": 5000.0}],
 "payments": [{"label": "…", "amount": 5000.0, "date": "…", "type": "RETENTION_RELEASE"}]}
```

## Structure

```
du/
  app.py                    interface Streamlit (4 pages + exemples + évaluation)
  analyze.py                analyse en ligne de commande
  run_evaluation.py         évaluation corpus vs vérité terrain
  du_engine/
    models.py               structures (Evidence, ExtractedField, FinancialEvent, statuts)
    pdf_reader.py           texte page par page, repérage des articles (pas d'OCR)
    extractor.py            règles d'extraction + preuves + contrôle des extraits
    calculations.py         calculs déterministes (dates, révision, seuils, écarts)
    events.py               champs -> événements (faits / calculs / hypothèses)
    pipeline.py             orchestration + saisies utilisateur
    corpus.py               chargement d'un dossier de contrat
    evaluation.py           métriques
    storage.py              stockage local et validations humaines
  scripts/generate_demo_pdfs.py
  data/{contracts,ground_truth,results,uploads,simulated}/
  tests/
  REPORT.md                 état honnête : ce qui marche, ce qui n'est pas fiable
```

## Moteur hybride v1 (par défaut depuis le 03/10/2026)

Pipeline : segmentation → candidats larges → interprétation (cadres sémantiques locaux ; Claude en option)
→ vérification stricte contre la source → normalisation → calculs déterministes → cohérence → revue humaine
obligatoire sur les catégories critiques. Détail : `docs/ARCHITECTURE_HYBRIDE.md`.

| Action | Commande |
|---|---|
| Analyse v1 d'un PDF | `python analyze.py chemin/CCAP.pdf [--notification 2026-12-20]` |
| Analyse v1 d'une extraction texte | `python analyze.py fichier.txt --text` |
| Analyse avec l'interpréteur Claude (optionnel) | `pip install anthropic` puis `ANTHROPIC_API_KEY=... python analyze.py CCAP.pdf --llm` |
| Ancien moteur regex (comparaison) | `python analyze.py --engine baseline chemin/CCAP.pdf` |
| Évaluation (échoue si faux négatif critique) | `python run_evaluation.py` (`--engine baseline`, `--no-fail`) |
| Régression real_001 (contrat de conception) | `python scripts/run_real_001_v1.py` |
| Tests | `python -m pytest -q` |

L'interface Streamlit utilise encore le moteur baseline : aucune modification d'interface n'a été faite tant que le moteur v1 n'est pas terminé.
