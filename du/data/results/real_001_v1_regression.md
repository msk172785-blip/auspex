# real_001 — régression moteur hybride v1

Contrat de CONCEPTION (déjà lu, ayant servi au diagnostic). Ce résultat n'est PAS une validation indépendante.
Interpréteur utilisé : cadres sémantiques locaux (FRAMES). Interpréteur LLM : non exécuté (aucune clé d'API dans l'environnement).
Entrée : extraction texte fournie par l'utilisateur, 40 pages ; annexes absentes.

## Événements retenus (preuves vérifiées)

| id | type | statut | revue humaine | acteur (base) | délai | conséquence | nombres | page / art. |
|---|---|---|---|---|---|---|---|---|
| E1 | PURCHASE_ORDER_BILLING | AUTO_EXTRACTED | oui | SUPPLIER (INFERRED_FROM_SECTION) |  |   | 12000 € PURCHASE_ORDER_ANNUAL_CEILING | p.2 / 1.1 |
| E2 | VARIABLE_SERVICE_BILLING | AUTO_EXTRACTED | non | UNKNOWN (-) |  |   |  | p.2 / 1.1 |
| E3 | CONSEQUENCE_IF_NO_ACTION | REVIEW_REQUIRED | oui | SUPPLIER (EXPLICIT) | 2 months before ANNIVERSARY | PRICE_KEPT UNFAVORABLE |  | p.7 / 4.3 |
| E4 | CONSEQUENCE_IF_NO_ACTION | REVIEW_REQUIRED | oui | BUYER (EXPLICIT) | 2 months before ANNIVERSARY | DEEMED_ACCEPTED FAVORABLE |  | p.7 / 4.3 |
| E5 | PRICE_REVISION | REVIEW_REQUIRED | oui | UNKNOWN (-) |  |   |  | p.7 / 4.3 |
| E6 | PRICE_REVISION_DEADLINE | REVIEW_REQUIRED | oui | SUPPLIER (INFERRED_FROM_SECTION) | 2 months before ANNIVERSARY |   |  | p.7 / 4.3 |
| E7 | SUPPLIER_ACTION_REQUIRED | AUTO_EXTRACTED | oui | SUPPLIER (EXPLICIT) |  |   |  | p.7 / 4.3 |
| E8 | SUPPLIER_ACTION_REQUIRED | REVIEW_REQUIRED | oui | SUPPLIER (PRONOUN) |  |   |  | p.7 / 4.3 |
| E9 | SUPPLIER_ACTION_REQUIRED | AUTO_EXTRACTED | oui | SUPPLIER (EXPLICIT) |  |   |  | p.7 / 4.3 |
| E10 | PRICE_REVISION_THRESHOLD | AUTO_EXTRACTED | oui | UNKNOWN (-) |  |   | 3 % CAP_ANNUAL, 9 % CAP_CUMULATIVE | p.8 / 4.2.3 |
| E11 | PRICE_REVISION_THRESHOLD | REVIEW_REQUIRED | oui | BUYER (-) |  |   |  | p.8 / 4.2.4 |
| E12 | REEXAMINATION_RIGHT | REVIEW_REQUIRED | non | SUPPLIER (EXPLICIT) | 30 days after RECEIPT |   | 80 % COST_SHARE, 20 % COST_SHARE | p.8 / 4.2.5 |
| E13 | ADVANCE_PAYMENT | AUTO_EXTRACTED | non | UNKNOWN (-) |  |   | 50000 € ADVANCE_ELIGIBILITY_THRESHOLD, 5 % ADVANCE_RATE, 65 % ADVANCE_REPAYMENT, 80 % ADVANCE_REPAYMENT | p.10 / 4.3 |
| E14 | LATE_PAYMENT_INTEREST | AUTO_EXTRACTED | non | UNKNOWN (-) |  |   |  | p.10 / 4.4.1 |
| E15 | PAYMENT_TERM | AUTO_EXTRACTED | non | BUYER (INFERRED_FROM_SECTION) | 30 days after RECEIPT |   |  | p.10 / 4.4.1 |
| E16 | BILLING_CONDITION | AUTO_EXTRACTED | oui | SUPPLIER (EXPLICIT) |  |   |  | p.11 / 4.4.1 |
| E17 | BILLING_CONDITION | AUTO_EXTRACTED | oui | SUPPLIER (EXPLICIT) |  |   |  | p.11 / 4.4.1 |
| E18 | CONSEQUENCE_IF_NO_ACTION | AUTO_EXTRACTED | oui | SUPPLIER (EXPLICIT) | 30 days after NOTIFICATION | DEEMED_ACCEPTED UNFAVORABLE |  | p.11 / 4.4.2 |
| E19 | CONSEQUENCE_IF_NO_ACTION | REVIEW_REQUIRED | oui | SUPPLIER (PRONOUN) | 8 days before OTHER | DEEMED_NOT_PERFORMED UNFAVORABLE |  | p.14 / 5.1.3 |
| E20 | PENALTY_EXPOSURE | REVIEW_REQUIRED | non | UNKNOWN (-) |  |   | 1000 € PENALTY_EXEMPTION_THRESHOLD, 100 € PENALTY_RATE, 50 € PENALTY_RATE | p.33 / 10 |

## Extraits (preuves)

- E1 PURCHASE_ORDER_BILLING :
  - p.2 art. 1.1 [EXACT] « Elles comprennent des prestations récurrentes et des prestations ponctuelles complémentaires qui feront l'objet de bons de commande spécifiques. »
  - p.6 art. 4.1 [EXACT] « Accord-cadre mono-attributaire à bons de commande, en application des articles R.2162-2, R.2162-4, R.2162-13 et R.2162-14 et ce, sans mention de minimum, et pour un montant annuel maximum de commandes arrêté à 12 000 € H »
- E2 VARIABLE_SERVICE_BILLING :
  - p.2 art. 1.1 [EXACT] « Elles comprennent des prestations récurrentes et des prestations ponctuelles complémentaires qui feront l'objet de bons de commande spécifiques. »
  - p.3 art. 1.5 [EXACT] « Les prestations ponctuelles sur bons de commande, pourront porter sur d'autres sites que ceux listés en annexe 1 du CCP. »
- E3 CONSEQUENCE_IF_NO_ACTION :
  - p.7 art. 4.3 [EXACT] « La demande de révision de prix devra parvenir deux mois avant la date de renouvellement du marché (soit la date « anniversaire ») par lettre recommandée avec accusé de réception. »
  - p.7 art. 4.3 [EXACT] « En cas de non-respect de ce délai, les prix de l'année en cours seront d'office reconduits pour une nouvelle période d'un an. »
- E4 CONSEQUENCE_IF_NO_ACTION :
  - p.7 art. 4.3 [EXACT] « La demande de révision de prix devra parvenir deux mois avant la date de renouvellement du marché (soit la date « anniversaire ») par lettre recommandée avec accusé de réception. »
  - p.7 art. 4.3 [EXACT] « Par ailleurs, l'absence de réponse de la part de l'administration dans ce délai de deux mois vaudra acceptation des nouveaux prix du titulaire. »
- E5 PRICE_REVISION :
  - p.7 art. 4.3 [EXACT] « Les prix du marché seront fermes la première année d'exécution. »
  - p.7 art. 4.3 [EXACT] « En cas de reconduction, ils seront révisés annuellement en début de période de reconduction, à chaque anniversaire, c'est à dire à la date de prise d'effet du marché. »
  - p.7 art. 4.3 [EXACT] « Les prix du marché seront révisés par application de la formule suivante : »
  - p.7 art. 4.3 [EXACT] « P=P0 (BtoB / BtoB0) − P : Prix révisé − Po : Prix initial − BtoB : Indices des prix de production des services français aux entreprises françaises (BtoB) - CPF 81.21 - Nettoyage courant, marché public - Prix de marché -  »
- E6 PRICE_REVISION_DEADLINE :
  - p.7 art. 4.3 [EXACT] « La demande de révision de prix devra parvenir deux mois avant la date de renouvellement du marché (soit la date « anniversaire ») par lettre recommandée avec accusé de réception. »
- E7 SUPPLIER_ACTION_REQUIRED :
  - p.7 art. 4.3 [EXACT] « Nota important L'attention du Titulaire est appelée sur le fait qu'il lui appartient de calculer le coefficient de révision applicable. »
- E8 SUPPLIER_ACTION_REQUIRED :
  - p.7 art. 4.3 [EXACT] « Il doit, lors de sa demande de révision des prix, fournir les éléments de détermination de cette révision (relevé des indices). »
- E9 SUPPLIER_ACTION_REQUIRED :
  - p.7 art. 4.3 [EXACT] « Le titulaire transmettra par ailleurs une décomposition du prix global et forfaitaire ainsi qu'un bordereau des prix unitaires révisé. »
- E10 PRICE_REVISION_THRESHOLD :
  - p.8 art. 4.2.3 [EXACT] « La variation des prix du marché est plafonnée à une augmentation maximale annuelle de 3% par rapport aux prix de l'année précédente. »
  - p.8 art. 4.2.3 [EXACT] « Il est donc précisé que l'augmentation des prix du marché ne pourra excéder 9 % sur la totalité de la durée de l'accord-cadre (4 ans au maximum). »
  - p.8 art. 4.2.3 [EXACT] « Dans le cas où l'application de la clause de révision des prix mentionnée à l'article 4.2.1. conduirait à une variation annuelle des prix unitaires de base supérieure à 3 %, le titulaire sera tenu d'exécuter les prestati »
- E11 PRICE_REVISION_THRESHOLD :
  - p.8 art. 4.2.4 [EXACT] « Dans le cas où les prix pratiqués ne pourraient satisfaire la clause butoir, le pouvoir adjudicateur se réserve le droit de résilier sans indemnité la partie non exécutée du marché. »
- E12 REEXAMINATION_RIGHT :
  - p.8 art. 4.2.5 [EXACT] « Dans ce cas, le titulaire peut adresser à l'acheteur, une demande comprenant : »
  - p.8 art. 4.2.5 [EXACT] « Par conséquent, 80% de cette augmentation sera prise en charge par le pouvoir adjudicateur et 20% par le titulaire. »
  - p.8 art. 4.2.5 [EXACT] « L'acheteur se prononce sur ladite demande dans un délai de 30 jours calendaires courant à compter de sa réception. »
- E13 ADVANCE_PAYMENT :
  - p.10 art. 4.3 [EXACT] « Sauf renoncement du titulaire porté à l'acte d'engagement, une avance lui sera mandatée dans les conditions spécifiées aux articles R. 2191-3, R. 2191-7 et R. 2391-16 du Code de la commande publique. »
  - p.10 art. 4.3 [EXACT] « Le montant de l'avance versée au titulaire n'est ni révisable ni actualisable. »
  - p.10 art. 4.3 [EXACT] « Cette avance sera mandatée sans formalité dans le délai d'un (1) mois après la date d'effet qui comporte commencement d'exécution des prestations prévues au marché. »
  - p.10 art. 4.3 [EXACT] « Conformément à l'option B de l'article 11.1 du CCAG-FCS, l'accord-cadre prévoit l'application des taux d'avance minimaux réglementaires fixés par l'article R. 2191-7 du Code de la commande publique, soit 5% de chaque bon »
- E14 LATE_PAYMENT_INTEREST :
  - p.10 art. 4.4.1 [EXACT] « En application de l'article L. 2192-13 et R. 2192-31 du même code, le dépassement du délai de paiement ouvre de plein droit et sans autre formalité pour le titulaire du marché, à compter du jour d'expiration du délai, au »
  - p.10 art. 4.4.1 [EXACT] « Les intérêts moratoires ne sont pas assujettis à la taxe sur la valeur ajoutée. »
  - p.10 art. 4.4.1 [EXACT] « Le taux des intérêts moratoires applicable est celui de l'intérêt légal en vigueur à la date à laquelle les intérêts ont commencé à courir, augmenté de huit points. »
- E15 PAYMENT_TERM :
  - p.10 art. 4.4.1 [EXACT] « En application des articles L. 2192-10 et R. 2192-10 du Code de la commande publique le paiement des sommes dues devra intervenir dans un délai de 30 jours à compter de la date de réception de la demande ou de la date d' »
- E16 BILLING_CONDITION :
  - p.11 art. 4.4.1 [EXACT] « L'émission de cette facture mensuelle est conditionnée à la validation par la commune du « procès-verbal de contrôle qualité » établi et transmis par le titulaire conformément à l'article 8.1 du présent cahier des clause »
- E17 BILLING_CONDITION :
  - p.11 art. 4.4.1 [EXACT] « L'émission de cette facture est conditionnée à la validation par la commune du « procès-verbal de contrôle qualité » établi et transmis par le titulaire conformément à l'article 8.1 du présent cahier des clauses particul »
- E18 CONSEQUENCE_IF_NO_ACTION :
  - p.11 art. 4.4.2 [EXACT] « Il est notifié au titulaire si la facture a été modifiée ou si elle a été complétée comme il est dit à l'alinéa précédent. »
  - p.11 art. 4.4.2 [EXACT] « Passé un délai de trente jours à compter de cette notification, le titulaire est réputé, par son silence, avoir accepté ce montant. »
- E19 CONSEQUENCE_IF_NO_ACTION :
  - p.14 art. 5.1.3 [EXACT] « Il communiquera la date de cette intervention à l'interlocuteur désigné de la commune, 8 jours avant la réalisation de la prestation. »
  - p.14 art. 5.1.3 [EXACT] « A défaut d'une telle communication, il sera réputé ne pas avoir réalisé l'opération. »
- E20 PENALTY_EXPOSURE :
  - p.33 art. 10 [EXACT] « Par dérogation à l'article 14.1.3 du CCAG, le titulaire n'est pas exonéré des pénalités dont le montant total ne dépasse pas 1 000 € HT pour l'ensemble de l'accord-cadre. »
  - p.33 art. 10 [EXACT] « 100€ par jour calendaire de retard et par planning, à Absence de transmission d'un planning compter du lendemain de la fin du délai de réponse du d'interventions titulaire et ce, jusqu'à transmission Absence sans remplac »
  - p.34 art. 10 [EXACT] « Rupture dans l'approvisionnement des 10€ par heure ouvrable de retard et par site, à partir du consommables mis à disposition des signalement de la collectivité et ce, jusqu'à usagers régularisation 50 € par jour calenda »
  - p.34 art. 10 [EXACT] « Absence du titulaire à une commission 100€ par constat entretien ou à un contrôle contradictoire 100€ par jour calendaire de retard à compter du Non-transmission par le titulaire de son lendemain de la fin du délai de tr »

## Faits du contrat

- Date de début : expression `max(2026-12-16, notification_date)` ; valeur = None ; au plus tôt = 2026-12-16 ; manquant = ['notification_date']
- Durée : initiale 12 mois ; reconductions [(2, 12), (1, 9)] ; maximum calculé 45 mois ; maximum énoncé 48 mois ; dernière date énoncée 2030-09-15 ; recalculée 2030-09-15
- Valeur annuelle du marché : None (le maximum des bons de commande n'est pas utilisé)
- Délai(s) de paiement : ['30 days after RECEIPT']

## Calcul déterministe des échéances de demande de révision

- Base : date de début AU PLUS TÔT = 16/12/2026
- Anniversaire n°1 = 16/12/2027 -> échéance = 16/12/2027 − 2 months = 16/10/2027
- Anniversaire n°2 = 16/12/2028 -> échéance = 16/12/2028 − 2 months = 16/10/2028
- Anniversaire n°3 = 16/12/2029 -> échéance = 16/12/2029 − 2 months = 16/10/2029
- Dates AU PLUS TÔT : elles décalent si la date réelle est postérieure (REVIEW_REQUIRED).

## Checklist des catégories critiques (revue humaine obligatoire)

- echeance_revision : FOUND ['E6']
- action_obligatoire_titulaire : FOUND ['E6', 'E7', 'E8', 'E9', 'E16', 'E17']
- forclusion_perte_de_droit : FOUND ['E3', 'E4', 'E18', 'E19']
- seuil_ou_plafond_revision : FOUND ['E10', 'E11']
- nouveau_prix_du : FOUND ['E5']
- avenant_modifiant_le_prix : NOT_FOUND []
- prestation_commandee_facturable : FOUND ['E1', 'E16', 'E17']

## Zones candidates non couvertes (REVIEW_REQUIRED)

- p.8 art. 4.2.5 ['PRICE_CHANGE'] : « ✓ L'exposé des causes à l'origine de l'augmentation des coûts d'exécution du marché ; ✓ L'étendue de cette augmentation, établie sur la base de justificatifs dont la production est extérieure au deman »
- p.32 art. 8.5 ['ECONOMIC_OBLIGATION_WITH_DEADLINE'] : « Lorsque la commune conclura à une absence de réalisation des prestations prévues au marché ou au bon de commande, le titulaire s'engage, pour toute saisine de la collectivité ayant pour objet l'absenc »

## Rejetées (REJECTED_UNSUPPORTED)

- aucune

## Anomalies du document (signalées, non corrigées)

- CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf : Numéro d'article 4.3 utilisé 2 fois : p.7 « Révision des prix » ; p.10 « Avance »
- CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf : Ordre non monotone : 4.3 (p.7) puis 4.2.3 (p.8)
- CCP_Lot1_Nettoyage_des_locaux_ 2026.pdf : Renvoi vers un article inexistant dans le document : « article 4.2.1. » (p.8)

## Contrôles de cohérence exécutés

- CAP != THRESHOLD vérifié
- plafonds annuel / cumulé distingués
- montant BDC ≠ valeur du marché
- fréquence opérationnelle ≠ fréquence de révision
- conséquence d'inaction ≠ action automatique favorable
- date conditionnelle non absolue
- durée calculée vs énoncée

## Signal baseline (regex)

- revision_exists = True (p.7) : expliqué par v1 = True
- cap_exists = True (p.8) : expliqué par v1 = True
- threshold_exists = True (p.8) : expliqué par v1 = True
- purchase_orders_exist = True (p.2) : expliqué par v1 = True
