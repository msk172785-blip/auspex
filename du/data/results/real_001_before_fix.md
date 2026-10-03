# real_001 — résultat du moteur AVANT correction

| | |
|---|---|
| Document | `CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf` — Cahier des clauses particulières, lot n°1 « Nettoyage et entretien des locaux », Commune de Gif-sur-Yvette, consultation 26-87209 |
| Nature | VRAI document de marché public. `SIMULATED_EXAMPLE = false` |
| Moteur | version 0.1.0, règles regex inchangées (`du_engine/` non modifié) |
| Date de référence des calculs | 03/10/2026 |
| Saisies utilisateur | aucune |
| Sortie brute | `data/results/real_001_before_fix.json` |

## 0. Limites de cette mesure (à lire d'abord)

1. Le PDF binaire n'a pas pu être téléchargé : le proxy réseau de l'environnement répond 403 sur radarmarchespublics.fr. Le moteur a tourné sur l'extraction texte fournie par l'utilisateur, recopiée dans `data/contracts/real_001/CCP_Lot1_Nettoyage_des_locaux_2026.txt`.
   - Les pages sont découpées d'après les pieds de page « Page N sur 40 ».
   - Tout le reste passe par les mêmes fonctions que pour un PDF (normalisation, repérage des articles, extraction, événements).
   - Les erreurs propres à `pypdf` (colonnes, tableaux) ne sont donc pas mesurées ici.
2. La source annonce 70 pages pour cette pièce, mais le texte fourni n'en contient que 40. Les annexes 1 à 6 ne sont pas analysées.
3. La section 7 compare la sortie du moteur à ma propre lecture du document. Cette lecture n'est pas une vérité terrain validée par un humain.
4. Un seul contrat : aucune précision globale ne peut en être déduite.

## 1. Clauses financières détectées par le moteur

| Champ | Valeur extraite | Statut | Conf. | Source (page / article attribué) |
|---|---|---|---|---|
| contract_title | les prestations de nettoyage et d'entretien des locaux - lot n°1 | AUTO_EXTRACTED | 0,80 | p. 2 / art. 1 |
| annual_amount | 12 000 € HT | AUTO_EXTRACTED | 0,85 | p. 6 / art. 4 |
| contract_duration | 12 mois (aucune reconduction) | AUTO_EXTRACTED | 0,80 | p. 5 / art. 3 |
| price_type | FERME / REVISABLE | REVIEW_REQUIRED | 0,50 | p. 7 / « 4.1.2 », p. 6 / 4.1.1 |
| revision_exists | oui | REVIEW_REQUIRED | 0,55 | p. 7 / « 4.1.2 » |
| revision_formula | `P=P0 (BtoB / BtoB0)` | REVIEW_REQUIRED | 0,65 | p. 7 / « 4.1.2 » |
| revision_type | FORMULE_A_VERIFIER | REVIEW_REQUIRED | 0,65 | p. 7 / « 4.1.2 » |
| revision_index | identifiant Insee 010766785 (aucun nom d'indice) | AUTO_EXTRACTED | 0,85 | p. 7 / « 4.1.2 » |
| base_index | « …mois de remise des offres, ce mois est appelé « mois zéro » » | REVIEW_REQUIRED | 0,75 | p. 7 / « 4.1.2 » |
| revision_frequency | TRIMESTRIELLE | AUTO_EXTRACTED | 0,80 | p. 14 / 5.1.3 |
| revision_trigger | [AUTOMATIQUE] | AUTO_EXTRACTED | 0,80 | p. 7 / « 4.1.2 » |
| cap_exists / cap_value | oui / 3 % | AUTO_EXTRACTED | 0,80 | p. 8 / 4.2.3 |
| threshold_exists / threshold_value | oui / 3 % de type DECLENCHEMENT | AUTO_EXTRACTED | 0,80 | p. 8 / 4.2.3 |
| purchase_orders_exist | oui | AUTO_EXTRACTED | 0,85 | p. 2 / art. 1 |
| variable_services_exist | oui | AUTO_EXTRACTED | 0,80 | p. 2 / art. 1 |
| late_payment_interest | oui | AUTO_EXTRACTED | 0,80 | p. 10 / 4.4.1 |

Champs rendus NOT_FOUND : contract_id, buyer, supplier, contract_end_date, supplier_action_required, supplier_action_description, deadline_rule, calculated_deadline, forfeiture_exists, forfeiture_consequence, amendments_exist, retention_exists, retention_rate, retention_release_rule, payment_terms, advance_payment, guarantee_period_months, final_balance_rule.

Événements produits (5) :

| # | Type | Sévérité | Statut | Source |
|---|---|---|---|---|
| 1 | PRICE_REVISION | medium | REVIEW_REQUIRED | p. 7 / « 4.1.2 » |
| 2 | PRICE_REVISION_THRESHOLD | medium | AUTO_EXTRACTED | p. 8 / 4.2.3 |
| 3 | PURCHASE_ORDER_BILLING | info | AUTO_EXTRACTED | p. 2 / 1 |
| 4 | VARIABLE_SERVICE_BILLING | info | AUTO_EXTRACTED | p. 2 / 1 |
| 5 | OTHER_FINANCIAL_RIGHT (intérêts moratoires) | info | AUTO_EXTRACTED | p. 10 / 4.4.1 |

Aucun événement CRITICAL n'a été produit.

## 2. Échéances détectées par le moteur

Aucune. `deadline_rule` et `calculated_deadline` sont NOT_FOUND, et aucun événement PRICE_REVISION_DEADLINE ni PRICE_REVISION_FORFEITURE n'a été produit.

## 3. Montants détectés par le moteur

| Montant | Rôle attribué par le moteur | Source |
|---|---|---|
| 12 000 € HT | montant annuel du marché (`annual_amount`) | p. 6 / art. 4 |
| 3 % | plafond (`cap_value`) et seuil de déclenchement (`threshold_value`) | p. 8 / 4.2.3 |

Aucun montant d'impact n'a été calculé (`potential_amount = null` partout) : le moteur n'avait ni coefficient, ni valeurs d'indices, ni formule interprétable.

## 4. Actions demandées au titulaire, détectées par le moteur

Aucune action liée à la révision (`supplier_action_required` NOT_FOUND).

Les actions affichées sont des textes génériques du moteur, pas des obligations lues dans le contrat :
- « Vérifier l'indice publié, calculer le coefficient et préparer la demande de révision. »
- « Contrôler que chaque bon de commande exécuté a été facturé… »
- « Vérifier que les quantités réellement exécutées sont toutes facturées. »
- « Vérifier les dates de paiement ; réclamer intérêts moratoires… »

## 5. Sources / pages / articles

Les 15 extraits distincts cités par le moteur ont tous été retrouvés littéralement dans le texte de leur page (`quote_verified = true`). Les numéros de page sont justes. Les numéros d'article sont faux à la page 7 :

| Extrait | Page | Article attribué | Article réel dans le document |
|---|---|---|---|
| « 4.3 - Révision des prix Les prix du marché seront fermes la première année d'exécution. » | 7 | 4.1.2 | 4.3 Révision des prix |
| Formule et définition BtoB / BtoB0 | 7 | 4.1.2 | 4.3 |
| « …ce mois est appelé « mois zéro » » | 7 | 4.1.2 | 4.2 Mode d'établissement des prix |
| « …seront d'office reconduits pour une nouvelle période d'un an. » | 7 | 4.1.2 | 4.3 |
| Clause butoir 3 % | 8 | 4.2.3 | 4.2.3 (numérotation du document lui-même incohérente, voir 7.2) |
| Fréquence « une fois par trimestre » | 14 | 5.1.3 | 5.1.3 (clause sans rapport avec la révision) |

## 6. Zones marquées REVIEW_REQUIRED par le moteur

| Champ / événement | Motif donné par le moteur |
|---|---|
| price_type | mentions contradictoires « ferme » / « révisable » |
| revision_exists | « Le document mentionne aussi des prix fermes » |
| revision_formula / revision_type | formule non reconnue comme paramétrique à un indice |
| base_index | confiance 0,75 < 0,80 |
| contract_start_date | `missing_information = date_notification` (preuve citée : mauvaise phrase, voir 7.3) |
| Événement PRICE_REVISION | manquent : formule interprétable ou coefficient, valeur I0, valeur In |

## 7. Ce que le moteur n'a pas réussi à comprendre

Comparaison avec ma lecture du texte (non validée par un humain).

### 7.1 Faux négatifs sur des événements CRITICAL

| # | Catégorie critique | Texte du contrat (extrait exact) | Page / article | Résultat moteur |
|---|---|---|---|---|
| C1 | Échéance de révision | « La demande de révision de prix devra parvenir deux mois avant la date de renouvellement du marché (soit la date « anniversaire ») par lettre recommandée avec accusé de réception. » | 7 / 4.3 | MANQUÉ |
| C2 | Action obligatoire du fournisseur | « L'attention du Titulaire est appelée sur le fait qu'il lui appartient de calculer le coefficient de révision applicable. Il doit, lors de sa demande de révision des prix, fournir les éléments de détermination de cette révision (relevé des indices). Le titulaire transmettra par ailleurs une décomposition du prix global et forfaitaire ainsi qu'un bordereau des prix unitaires révisé. » | 7 / 4.3 (« Nota important ») | MANQUÉ |
| C3 | Forclusion / perte d'un droit | « En cas de non-respect de ce délai, les prix de l'année en cours seront d'office reconduits pour une nouvelle période d'un an. » | 7 / 4.3 | MANQUÉ, et sens inversé : lu comme « révision AUTOMATIQUE » |
| C4 | Forclusion / perte d'un droit (facturation) | « Passé un délai de trente jours à compter de cette notification, le titulaire est réputé, par son silence, avoir accepté ce montant. » (montant de facture rectifié par l'acheteur) | 11 / 4.4.2 | MANQUÉ |
| C5 | Seuil / plafond de révision | « La variation des prix du marché est plafonnée à une augmentation maximale annuelle de 3% … ne pourra excéder 9 % sur la totalité de la durée » | 8 / 4.2.3 | Détecté, mais mal qualifié : le plafond est classé aussi en seuil de DECLENCHEMENT, et le plafond cumulé de 9 % est ignoré |
| C6 | Nouveau prix dû | Révision annuelle à chaque reconduction ; « La mise à jour des prix s'effectuera en même temps que la première facturation des exercices de reconduction. » Et : « l'absence de réponse de la part de l'administration dans ce délai de deux mois vaudra acceptation des nouveaux prix du titulaire. » | 7 / 4.3 | Partiel : PRICE_REVISION détecté (REVIEW_REQUIRED), mais ni la date d'application ni l'acceptation tacite des nouveaux prix |
| C7 | Avenant modifiant le prix | Aucun avenant fourni. Clause de réexamen : le titulaire peut demander une prise en charge de 80 % d'une hausse de coûts imprévisible, l'acheteur répond sous 30 jours calendaires. | 8 / 4.2.5 | Pas d'avenant attendu. La clause de réexamen n'est pas détectée |
| C8 | Prestation commandée potentiellement facturable | Bons de commande sur BPU, maximum 12 000 € HT/an. « L'émission de cette facture est conditionnée à la validation par la commune du « procès-verbal de contrôle qualité » établi et transmis par le titulaire » | 6 / 4.1, 11 / 4.4.1 | Détecté en INFO. La condition de facturation (PV qualité à transmettre) est manquée |

Bilan sur les catégories critiques :
- 4 manqués purs (C1, C2, C3, C4) ;
- 1 détecté avec un sens faux (C5) ;
- 2 partiels (C6, C8) ;
- C7 sans objet, faute d'avenant.

C1, C2 et C3 forment exactement le scénario central de DÛ (révision à demander sous peine de perdre un an de révision), et le moteur l'a manqué.

### 7.2 Erreurs de sens sur ce qui a été détecté (faux positifs ou mauvaises valeurs)

| Champ | Moteur | Lecture du texte | Gravité |
|---|---|---|---|
| annual_amount | 12 000 € HT, AUTO_EXTRACTED 0,85 | C'est le montant annuel MAXIMUM des bons de commande, pas le montant annuel du marché. Le forfait annuel n'est pas dans le CCP (il est dans la DPGF) | Élevée : tout calcul d'impact serait faux, avec une confiance affichée haute |
| threshold_value | 3 %, DECLENCHEMENT | C'est une clause butoir (plafond). Appliquée par le module de calcul comme seuil de déclenchement, elle annulerait toute révision inférieure à 3 % | Élevée : inversion de sens |
| revision_trigger | AUTOMATIQUE | « d'office reconduits » décrit la conséquence d'un oubli (prix NON révisés) ; la révision est en réalité à la demande du titulaire | Élevée : inversion de sens |
| revision_frequency | TRIMESTRIELLE (nettoyage des conteneurs, p. 14) | ANNUELLE (« révisés annuellement … à chaque anniversaire »). Cause : « prévision » contient la sous-chaîne « révis » | Moyenne |
| contract_duration | 12 mois, sans reconduction | 1 an + 2 reconductions expresses d'1 an + 1 reconduction de 9 mois, soit au plus 45 mois, jusqu'au 15/09/2030 (durée totale ≤ 4 ans) | Moyenne |
| contract_start_date | REVIEW_REQUIRED, preuve = phrase sur l'affermissement des tranches (p. 3) | « à compter du 16 décembre 2026 ou à compter de sa notification au titulaire si celle-ci a lieu à une date ultérieure » (p. 5) : date conditionnelle | Moyenne : bon statut, mauvaise preuve |
| Articles page 7 | 4.1.2 | 4.2 et 4.3. Le titre « 4.3 - Révision des prix » n'est pas reconnu (séparateur « - ») | Moyenne |

La numérotation du document est elle-même incohérente : « 4.3 » est utilisé deux fois (Révision des prix, puis Avance), la clause butoir est numérotée « 4.2.3 » après le 4.3, et le texte renvoie à un « article 4.2.1 » qui n'existe pas. Un moteur doit le signaler, pas le corriger silencieusement.

### 7.3 Autres clauses financières manquées (hors catégories critiques)

| Clause | Extrait | Page / article |
|---|---|---|
| Délai de paiement | « …le paiement des sommes dues devra intervenir dans un délai de 30 jours à compter de la date de réception de la demande ou de la date d'admission des prestations. » | 10 / 4.4.1 |
| Avance | « Sauf renoncement du titulaire porté à l'acte d'engagement, une avance lui sera mandatée… soit 5% de chaque bon de commande d'un montant supérieur à 50 000 € HT », conditionnée à une garantie à première demande | 10 / 4.3 (Avance) |
| Taux des intérêts moratoires | « …intérêt légal en vigueur … augmenté de huit points. » | 10 / 4.4.1 |
| Facturation mensuelle du forfait | « …facture représentant 1/12ème du montant global et forfaitaire annuel… émise par le titulaire en première semaine du mois « m+1 ». » | 11 / 4.4.1 |
| Pénalités (risque financier) | Tableau de l'article 10 : 100 €/jour par planning non transmis, 200 €/jour par site pour absence de prestation d'entretien courant, etc. Le titulaire n'est pas exonéré des pénalités ≤ 1 000 € HT | 33-35 / 10 |
| Échéances opérationnelles sous pénalité | Plannings dans les 20 jours après notification et dans les 20 jours après chaque anniversaire ; rapport annuel un mois avant le terme de chaque année ; plannings Val Fleury / Terrasse au 31 juillet ; planification estivale au 31 mai | 20-21 / 6.9, 6.13 |
| Renonciation contractuelle | « Le titulaire ne pourra donc en aucun cas se prévaloir d'éventuelles conséquences financières résultant de ce contexte… » | 6 / art. 4 |
| Tranches optionnelles | 18 tranches, affermissement sous 48 mois au plus ; « ne pourra prétendre à aucune indemnité » en cas de non-affermissement | 3 / 1.3 |
| Acheteur | Commune de Gif-sur-Yvette : page de garde éclatée par la mise en page, pas de libellé « Acheteur : » | 1 |

Absences correctement rendues : aucune retenue de garantie ni délai de garantie dans ce texte (NOT_FOUND exact) ; aucun numéro de marché dans le CCP.

### 7.4 Ce qu'un moteur correct aurait dû calculer

Ces valeurs ne sont pas produites par le moteur. Elles illustrent la sortie attendue.

- Date de prise d'effet : 16/12/2026, ou la date de notification si elle est postérieure. Non connue à ce jour : REVIEW_REQUIRED, `missing_information = date_notification`.
- Hypothèse : prise d'effet le 16/12/2026, sans reconduction anticipée. Alors :
  - première révision possible : 16/12/2027, début de la 1re reconduction ;
  - la demande doit être reçue au plus tard 2 mois avant, soit le 16/10/2027, par LRAR ;
  - même règle les années suivantes : 16/10/2028, puis 16/10/2029.
  - Une reconduction anticipée décale l'anniversaire (art. 3.1) : à recalculer.
- Coefficient : formule `P = P0 × (BtoB / BtoB0)`, sans partie fixe, indice Insee 010766785. Plafond : 3 % par an et 9 % cumulés.
- Impact : non calculable sans le montant de la DPGF ni les valeurs d'indice. Le 12 000 € HT ne doit pas servir de base.

### 7.5 Catégories d'erreurs (causes générales, pas propres à ce contrat)

| Code | Catégorie | Exemples ci-dessus |
|---|---|---|
| E1 | Formulation sans sujet explicite : voix passive, pronom, futur à valeur d'obligation, « il lui appartient » | C1, C2 |
| E2 | Synonymes de la date de référence et des déclencheurs (« date de renouvellement », « échéance annuelle ») | C1 |
| E3 | Conséquence d'un oubli exprimée sans marqueur prévu (« En cas de non-respect… reconduits d'office ») ; un mot comme « d'office » change de sens selon le contexte | C3, revision_trigger |
| E4 | Rôle d'un nombre mal compris : un maximum de commandes pris pour un montant annuel, un plafond pris pour un seuil, cumul de 9 % ignoré | annual_amount, C5 |
| E5 | Correspondance par sous-chaîne sans frontière de mot (« prévision » ⊃ « révis ») | revision_frequency |
| E6 | Structure documentaire : titres « 4.3 - … » non reconnus, numérotation incohérente du document | articles page 7 |
| E7 | Information répartie sur plusieurs phrases ou paragraphes ; dates conditionnelles (« X ou Y si postérieure ») | C1-C3, contract_start_date |
| E8 | Notions absentes du schéma : acceptation tacite (dans les deux sens), condition de facturation, pénalités, clause de réexamen, renonciation | C4, C6, C7, C8 |
| E9 | Formule de révision sans partie fixe non interprétée | revision_formula |
| E10 | Entrée incomplète : PDF original non accessible, annexes absentes | section 0 |

Ajouter des synonymes ne réglerait que E2 et une partie de E3. E1, E3, E4, E7 et E8 demandent une interprétation du sens.
