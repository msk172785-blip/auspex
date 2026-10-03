# DÛ v0 — rapport d'état

Date : 03/10/2026. Version du moteur : 0.1.0.

## 1. Ce qui fonctionne (vérifié par les tests et une exécution réelle)

- Lecture des PDF texte page par page, avec repérage des articles (« Article 4.3 », « Art. 12 »). L'article actif se reporte d'une page à l'autre.
- Extraction par règles de 37 champs : les 31 champs contractuels de la spécification et 6 champs complémentaires (taux et règle de libération de la retenue, intérêts moratoires, avance, délai de garantie, solde). Les 7 autres attributs de la spécification (type d'événement, document, page, article, extrait, confiance, statut) sont portés par chaque preuve et chaque événement.
- Chaque extrait est recontrôlé littéralement dans le texte de la page. Un test vérifie que tout champ de nature FACT a une preuve vérifiée.
- Détection de la révision : type de prix, formule, indice et identifiant, indice de base, fréquence, déclencheur, action du fournisseur, règle de délai (« deux mois avant la date anniversaire », « 30 jours à compter de la date anniversaire »), forclusion, seuil de déclenchement, plafond.
- Négations gérées : « il n'est pas prévu de retenue de garantie », « prix fermes et non révisables », « il n'est pas prévu d'avance ».
- Calculs déterministes, avec étapes affichées :
  - prochaine date anniversaire et échéance de demande ;
  - coefficient de révision pour une formule paramétrique à un seul indice ;
  - nouveau prix et écart, avec seuil et plafond ;
  - écart d'avenant ;
  - bon de commande non facturé ;
  - date de libération de la retenue de garantie.
- Information manquante : sans date de début ou de notification, l'échéance n'est pas calculée. L'événement passe en `REVIEW_REQUIRED` avec `missing_information = date_notification`, et aucun montant n'est affiché sans montant annuel ni coefficient.
- Les quatre scénarios simulés produisent les montants attendus (6 600 €, 1 700 €, 4 800 €, 12 500 €), marqués comme simulés.
- Interface Streamlit testée deux fois : par `streamlit.testing` (test automatique) et dans Chromium (dépôt réel d'un PDF, cartes d'alerte, page Preuves).
- Stockage local des PDF déposés et des analyses, et validation humaine enregistrée.
- Évaluation automatique : `python run_evaluation.py`.
- Tests : 35 réussis, 1 échec attendu documenté (`xfail`, limite de vocabulaire).

## 2. Résultats d'évaluation actuels — à lire avec prudence

Corpus : 8 contrats, tous des EXEMPLES SIMULÉS rédigés par l'auteur des règles. Les règles ont été écrites en voyant les documents 1 à 7. Ces chiffres prouvent que le harnais fonctionne. Ils ne mesurent pas la performance sur de vrais contrats.

| Mesure | Valeur |
|---|---|
| Événements attendus / détectés | 27 / 24 |
| TP / FP / FN | 24 / 0 / 3 |
| dont FN critiques (à échéance) | 2 |
| Recall / recall pondéré / precision | 88,9 % / 84,4 % / 100 % |

Toutes les erreurs de rappel viennent de `sim_008`. Ce document a été rédigé exprès avec un vocabulaire non couvert (« ajustement tarifaire », « échéance annuelle ») et n'a pas servi à ajuster les règles. DÛ y manque la révision, l'échéance et la forclusion : c'est le type d'échec le plus grave, et il est attendu sur de vrais contrats.

Une erreur de page (`sim_003`) vient de la vérité terrain : la page 1 mentionne aussi les bons de commande. Elle a été laissée telle quelle, sans retoucher la vérité terrain après coup.

## 3. Ce qui n'est pas encore fiable (liste honnête)

1. Aucun vrai contrat n'a été testé. Le réseau de l'environnement de développement bloquait les sites publics (.gouv.fr, sites de collectivités) : aucun CCAP réel n'a pu être téléchargé. Le livrable « au moins un exemple réel de contrat analysable » n'est donc pas rempli. Le moteur accepte n'importe quel PDF texte, mais sa précision sur de vrais CCAP est inconnue.
2. Les règles regex sont fragiles hors vocabulaire. Synonymes, tournures inhabituelles, clauses renvoyant au CCAG ou à une annexe (« conformément à l'article X du CCAG-FCS ») : faux négatifs probables, y compris sur des échéances.
3. Pas d'OCR : un PDF scanné est signalé et rien n'est extrait.
4. Les tableaux (BPU, DPGF) et les mises en page en colonnes sont mal lus par `pypdf`. Une formule coupée sur plusieurs lignes peut être tronquée.
5. Formules multi-indices : reconnues mais non calculées (`REVIEW_REQUIRED`), la saisie du coefficient est demandée. Les formules avec terme de raccordement, arrondis spécifiques ou décalage d'indice (« mois m-3 ») ne sont pas interprétées.
6. Indices : DÛ ne télécharge pas les valeurs INSEE. Le coefficient ou les valeurs d'indices doivent être saisis.
7. Date anniversaire : l'hypothèse « anniversaire = anniversaire de la date de début saisie » est déclarée dans chaque événement. Elle peut être fausse si le contrat la définit autrement (notification, mois zéro, date fixe).
8. Clause butoir et clause de sauvegarde : détectées et signalées, mais non appliquées au calcul.
9. Rapprochement factures et bons de commande : JSON structuré uniquement, pas de lecture de factures PDF. L'appariement se fait par code article ou référence de BC exacte : une facture sans référence n'est pas reconnue.
10. Retenue de garantie : les réserves à la réception, la caution de substitution et les prolongations du délai de garantie ne sont pas gérées.
11. Les niveaux de confiance sont des constantes fixées par règle, non calibrées. 0,85 ne signifie pas « 85 % de chances d'être juste ».
12. Champs d'identité (acheteur, objet, n° de marché) : extraits seulement si une ligne « Libellé : valeur » existe dans les 3 premières pages.
13. Sévérité : seuils arbitraires (critique si l'échéance tombe dans les 60 jours, ou dans les 120 jours en cas de forclusion).

## 4. Écart assumé par rapport à l'exemple JSON de la spécification

L'exemple de la spécification affiche `"status": "VALIDATED"`. Le moteur ne produit jamais ce statut seul : il produit `AUTO_EXTRACTED`, et seul un humain peut valider. C'est l'application stricte de la règle « ne jamais marquer une extraction comme validée uniquement parce qu'une machine l'a produite ».

## 5. Prochaines étapes recommandées

1. Déposer 5 à 10 vrais CCAP dans `data/contracts/` avec leur vérité terrain, et mesurer avant toute amélioration.
2. Ajouter une extraction assistée par LLM, uniquement comme proposition : extrait obligatoire, contrôle littéral par `verify_quote`, statut toujours `REVIEW_REQUIRED`, comparaison avec les règles.
3. Ajouter l'OCR (Tesseract) pour les PDF scannés, en marquant explicitement le niveau de confiance OCR.
4. Ajouter la récupération des indices INSEE (séries BDM) pour calculer le coefficient sans saisie.
