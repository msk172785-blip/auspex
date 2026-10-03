# DÛ — architecture hybride proposée (v1, non implémentée)

Statut : proposition de conception. Aucune ligne de ce document n'est encore codée.
Les règles regex actuelles (`du_engine/extractor.py`) sont gelées et deviennent le BASELINE de comparaison.

Point de départ : les erreurs mesurées sur le premier vrai contrat (`data/results/real_001_before_fix.md`, catégories E1 à E10).

## 1. Principes

1. Le LLM interprète ; il ne prouve jamais. Une preuve est un extrait retrouvé dans le texte de la page, contrôlé par du code déterministe.
2. Toute affirmation sans extrait retrouvé reçoit le statut `REJECTED_UNSUPPORTED`. Elle n'est jamais affichée comme un fait (elle reste dans le journal d'audit).
3. Aucun calcul de date ou de montant n'est fait par le LLM : il fournit des paramètres normalisés, Python calcule.
4. Les numéros de page et d'article viennent de la structure du document (code), pas du LLM.
5. Le moteur doit se prononcer explicitement sur chaque catégorie critique : FOUND, ABSENT (avec les sections examinées) ou REVIEW_REQUIRED. Le silence est interdit.
6. `VALIDATED` reste réservé à l'humain.
7. Aucune règle propre à un document (ville, acheteur, numéro de consultation).

## 2. Pipeline

```
PDF
 └─ S0 Ingestion ............ texte page par page + offsets, provenance, contrôle de complétude
 └─ S1 Structuration ........ arbre des sections (titres, articles), anomalies de numérotation
 └─ S2 Candidats (rappel max) union : baseline regex  ∪  classification LLM de TOUTES les sections
 └─ S3 Interprétation LLM ... affirmations structurées, chacune avec extrait(s) exact(s)
 └─ S4 Vérification ......... extrait retrouvé ? valeur ancrée dans l'extrait ? sinon REJECTED_UNSUPPORTED
 └─ S5 Normalisation ........ schéma JSON fermé (enums), rôles des montants, types de clauses
 └─ S6 Calculs Python ....... échéances, coefficients, plafonds, dates conditionnelles
 └─ S7 Cohérence ............ règles croisées, désaccords baseline/LLM, checklist critique
 └─ S8 Statuts .............. AUTO_EXTRACTED | REVIEW_REQUIRED | REJECTED_UNSUPPORTED | (VALIDATED humain)
```

### S0 — Ingestion

- Texte par page avec offsets de caractères. Extracteur principal `pypdf`, et un second extracteur sensible à la mise en page (pdfplumber ou PyMuPDF) pour les tableaux et les colonnes. Les deux textes sont conservés.
- Pages sans texte : marquées `NO_TEXT_LAYER`. L'OCR éventuelle est tracée comme source dégradée, avec un plafond de confiance.
- Contrôle de complétude : nombre de pages annoncé (« Page N sur M », métadonnées) comparé au nombre reçu, annexes référencées comparées aux annexes fournies. Tout écart devient un avertissement (cas E10 : 40 pages reçues pour 70 annoncées).
- Provenance enregistrée : URL, empreinte du fichier, extracteur utilisé.

### S1 — Structuration

- Détection de titres par motifs généraux de numérotation : « ARTICLE 4 : », « Article 4.3 – », « 4.3 - Titre », « 4.2.3 Titre », « a) », puces. Le séparateur, la casse et les tirets typographiques sont libres (corrige E6).
- Chaque phrase est rattachée à une section, avec son étendue de pages.
- Anomalies signalées sans être corrigées : numéro d'article en double, ordre non monotone, renvoi vers un article inexistant (« article 4.2.1 »).
- Unité de travail : la section (titre + paragraphes), pas la phrase isolée (corrige en partie E7).

### S2 — Recherche large des clauses candidates (objectif : rappel)

Deux canaux combinés :

1. Baseline regex existante, corrigée seulement pour les défauts techniques non sémantiques : frontières de mot, pour éviter que « prévision » soit pris pour « révis » (E5).
2. Classification LLM de chaque section du document. Un CCP de 40 pages tient dans un seul contexte, on peut donc tout classer sans pré-filtre lexical. Le LLM attribue à chaque section zéro, une ou plusieurs catégories économiques :
   - révision ;
   - échéance ;
   - action du titulaire ;
   - perte de droit ;
   - plafond, seuil ;
   - montant ;
   - bons de commande ;
   - facturation ;
   - paiement ;
   - avance ;
   - retenue ;
   - pénalités ;
   - modification ou réexamen ;
   - acceptation tacite ;
   - autre droit financier.

Le moindre doute suffit à garder une section. Le critère de réussite de S2 : 100 % des clauses critiques de la vérité terrain présentes parmi les candidats, mesuré séparément de S3.

### S3 — Interprétation sémantique (LLM)

Entrée : une section candidate, sa voisine précédente et suivante, son titre, les sections qu'elle cite (« dans les conditions de l'article 4.3 »).

Sortie imposée par schéma (appel d'outil avec schéma JSON strict), sous forme d'une liste d'affirmations :

```json
{
  "claim_type": "REVISION_REQUEST_DEADLINE",
  "value": {"amount": 2, "unit": "months", "direction": "before", "reference_event": "RENEWAL_ANNIVERSARY"},
  "actor": "TITULAIRE",
  "obligation_strength": "MANDATORY",
  "consequence_if_missed": {"type": "PRICE_KEPT", "duration": {"amount": 1, "unit": "years"}},
  "evidence": [{"page": 7, "quote": "La demande de révision de prix devra parvenir deux mois avant la date de renouvellement du marché"}],
  "uncertainty": "LOW",
  "notes": "Voix passive : le demandeur est le titulaire (cf. Nota important, même section)."
}
```

Consignes du prompt, valables pour tous les contrats :
- recopier les extraits mot pour mot ;
- identifier l'acteur même en voix passive, avec un pronom ou une tournure comme « il lui appartient » (E1) ;
- préciser le rôle de chaque nombre (E4) ;
- préciser la polarité d'une conséquence : pour qui c'est favorable ou défavorable (E3) ;
- repérer les renvois au CCAG sans en déduire le contenu : ils produisent un REVIEW_REQUIRED ;
- ne jamais compléter une information absente.

Modèle : Claude via l'API Anthropic. Le modèle et ses paramètres seront choisis à l'implémentation et figés pour chaque campagne d'évaluation.

### S4 — Vérification obligatoire contre le texte original

Pour chaque extrait :
1. Normalisation identique des deux côtés : espaces, apostrophes, ligatures, césures, tirets.
2. Recherche exacte dans la page annoncée, ce qui donne `SUPPORTED_EXACT`.
3. Sinon, recherche exacte dans tout le document, ce qui donne `SUPPORTED_EXACT_OTHER_PAGE`. La page est corrigée et l'écart journalisé.
4. Sinon, correspondance approchée, par exemple une similarité de jetons au moins égale à 0,95 sur une longueur au moins égale à 90 % de l'extrait. Le texte réellement trouvé est stocké, et le résultat est `SUPPORTED_FUZZY`, forcé en REVIEW_REQUIRED.
5. Sinon : `REJECTED_UNSUPPORTED`.

Ancrage de la valeur : chaque nombre, date ou pourcentage de `value` doit apparaître dans l'un des extraits, en chiffres ou en lettres (« deux » = 2), ou venir d'un calcul de S6. Sinon, l'affirmation est rejetée.

Chaque champ conserve : document, page, article (pris dans S1), extrait proposé, texte réellement retrouvé, type de correspondance.

### S5 — Normalisation

Schéma fermé, avec des enums plutôt que du texte libre :
- `reference_event` : ANNIVERSARY, RENEWAL_ANNIVERSARY, NOTIFICATION, EFFECTIVE_DATE, INVOICE_NOTIFICATION, RECEPTION, …
- `amount_role` : ANNUAL_CONTRACT_VALUE, PO_ANNUAL_MAX, PO_ANNUAL_MIN, ADVANCE_ELIGIBILITY_THRESHOLD, PENALTY_UNIT, SUBCONTRACT_DIRECT_PAYMENT_THRESHOLD, …
- `price_variation_clause` : TRIGGER_THRESHOLD (seuil de déclenchement), CAP_ANNUAL, CAP_CUMULATIVE, SAFEGUARD_TERMINATION. La confusion plafond / seuil (E4) devient une erreur de schéma détectable.
- `tacit_acceptance` : bénéficiaire TITULAIRE ou ACHETEUR, délai, événement déclencheur (E8).
- Dates conditionnelles : `{"type": "LATER_OF", "candidates": ["2026-12-16", "NOTIFICATION_DATE"]}` (E7).

Nouveaux types d'événements nécessaires (E8) : TACIT_ACCEPTANCE_RISK, BILLING_CONDITION, PENALTY_EXPOSURE, REEXAMINATION_RIGHT, ADVANCE_PAYMENT. À valider avec l'utilisateur avant de les ajouter.

### S6 — Calculs déterministes

Module actuel, étendu :
- formule à rapport pur `P = P0 × (I/I0)` ;
- plafond annuel et plafond cumulé ;
- dates conditionnelles (`LATER_OF`) : si une seule candidate est connue, l'échéance est REVIEW_REQUIRED avec la date au plus tôt ;
- décalage d'anniversaire en cas de reconduction anticipée (paramètre saisi).

### S7 — Contrôle de cohérence

- Règles croisées. Exemples :
  - une révision à la demande du titulaire sans échéance trouvée donne REVIEW_REQUIRED ;
  - une perte de droit sans délai, idem ;
  - un `ANNUAL_CONTRACT_VALUE` issu d'une phrase « maximum de commandes » est rejeté ;
  - un plafond utilisé comme seuil est rejeté.
- Désaccord entre la baseline regex et le LLM : REVIEW_REQUIRED, journalisé.
- Deux passes LLM indépendantes (prompts ou ordres différents) : tout désaccord sur une catégorie critique donne REVIEW_REQUIRED.
- Checklist critique explicite (section 3).

### S8 — Statuts

| Statut | Condition |
|---|---|
| AUTO_EXTRACTED | extrait `SUPPORTED_EXACT` + valeur ancrée + cohérence OK + accord des deux passes ou de la baseline |
| REVIEW_REQUIRED | correspondance approchée, désaccord, information manquante, ambiguïté, anomalie de document |
| REJECTED_UNSUPPORTED | extrait introuvable ou valeur non ancrée. Jamais affiché comme fait |
| VALIDATED | validation humaine uniquement |

## 3. Événements critiques et tests

Catégories critiques :
1. échéance de révision ;
2. action obligatoire du fournisseur ;
3. forclusion ou perte d'un droit ;
4. seuil ou plafond de révision ;
5. nouveau prix dû ;
6. avenant modifiant le prix ;
7. prestation commandée potentiellement facturable.

Dans la vérité terrain, chaque événement porte `"critical": true` (voir `data/ground_truth/real_001.json`, brouillon à valider). Test d'évaluation à implémenter : tout faux négatif sur un événement `critical` d'un contrat validé fait échouer `pytest` et renvoie un code de sortie non nul pour `run_evaluation.py`.

## 4. Correspondance erreurs → étapes

| Erreur | Étape qui la traite |
|---|---|
| E1 sujet implicite, voix passive, futur d'obligation | S3 (acteur explicite) + S7 |
| E2 synonymes de dates de référence | S3 + enum `reference_event` (S5) |
| E3 conséquence sans marqueur, polarité | S3 (`consequence_if_missed`, polarité) + S7 |
| E4 rôle des nombres | S5 `amount_role`, `price_variation_clause` + S7 |
| E5 sous-chaînes | S2 (frontières de mot dans la baseline) |
| E6 titres, numérotation | S1 |
| E7 information répartie, dates conditionnelles | S1 (unité = section) + S3 (contexte élargi) + S5 `LATER_OF` |
| E8 notions absentes du schéma | S5 (nouveaux types, à valider) |
| E9 formule à rapport pur | S6 |
| E10 entrée incomplète | S0 (contrôle de complétude) |

## 5. Protocole d'évaluation anti-surapprentissage

- Corpus réel séparé en DEV (sert à concevoir les prompts et les règles) et TEST (jamais consulté pendant la conception). `real_001` a déjà été lu pour ce diagnostic : il passe en DEV, et les mesures de généralisation se feront sur d'autres contrats.
- Interdit : chaînes propres à un document dans les règles ou les prompts ; exemples tirés du TEST dans les prompts.
- Toute modification de règle ou de prompt est évaluée sur l'ensemble du corpus, pas sur le seul contrat qui a échoué.
- Les rapports d'évaluation séparent toujours simulé et réel, et DEV et TEST.
- Variabilité du LLM : chaque campagne exécute N passes et publie la variance des résultats critiques.

## 6. Confidentialité

L'envoi d'un document à une API externe doit être activé explicitement par l'utilisateur. Les DCE publics posent peu de difficulté ; les factures et les contrats clients en posent davantage. Sans activation, le moteur fonctionne en mode baseline local, avec ses limites affichées.

## 7. Plan d'implémentation (après accord)

1. S0 et S1 (ingestion, structuration, anomalies), avec leurs tests.
2. Schéma S5 et vérificateur S4, testés sans LLM sur des affirmations fabriquées (vraies, fausses, approchées).
3. S2 et S3 (appels LLM), journal d'audit.
4. S7 et S8, checklist critique, test d'échec sur faux négatif critique.
5. Ré-exécution sur real_001 (rapport « after »), puis sur de nouveaux contrats non consultés.
