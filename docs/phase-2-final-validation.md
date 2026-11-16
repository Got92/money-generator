# Validation combinée — lots Atlas 06 à 13

Validation du 16 novembre 2026, sur les huit branches empilées à partir de `origin/main` : `45d1c891f58df8b1029f6629aad4966117eddd67`. Les PR des lots précédents étaient fusionnées avant le départ. Huit agents Terra 6.1 High ont produit les lots ; l’orchestrateur a revu les résultats, résolu les conflits et raccordé les interfaces. `origin/main` n’a pas été modifié.

## Résultats

| Contrôle | Résultat |
|---|---|
| Tests JavaScript, `npm test` | 87 réussis, aucun échec |
| Tests Python, `ATLAS_DB=/chemin/temporaire/test.sqlite .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | 65 réussis, aucun échec |
| Chromium, `npm run test:browser` | 11 parcours réussis |
| Diff Git et conflits | `git diff --check` propre ; aucun marqueur de conflit dans les sources |
| Référence avant les huit lots | 73 tests JS, 40 Python et 3 parcours Chromium réussis |

Les parcours Chromium couvrent les performances et historiques existants, l’allocation, les états financiers, le tableau de bord entreprise, le scoring, les multiples, les scénarios, les analyses avancées, les cibles et le renforcement. Les sélecteurs de formulaires sont délimités pour éviter les collisions de noms entre composants ; les fixtures attendent la fin de l’initialisation avant de remplacer leur état.

`scripts/check-phase2-integration-browser.mjs` utilise les vrais modules de calcul et les vrais stores SQLite, avec uniquement un fournisseur de données synthétique. Il vérifie les ratios annuels et TTM, le score et ses captures, les pairs du même secteur, les huit multiples, les scénarios et cibles enregistrés, leur chargement dans la synthèse et le simulateur, puis l’absence de changement des transactions et de la révision d’état pendant l’analyse. Une sauvegarde du portefeuille conserve les tables de recherche et de configuration.

Les tests unitaires vérifient aussi les devises et périodes incompatibles, les observations manquantes, la conservation des révisions et migrations, FCFF/FCFE, la conversion EV vers fonds propres, les calculs de rendement, les limites du reverse DCF, les frais, le PRU et le change. Les nouvelles mesures d’allocation du capital exigent des observations annuelles comparables et n’utilisent pas le prix comme mesure de qualité.

Toutes les bases sont temporaires et les entreprises de test explicitement synthétiques. Aucun test n’ouvre une base personnelle. Les dépendances Python du projet, les dépendances npm et Chromium sont nécessaires ; `ATLAS_CHROMIUM` et `ATLAS_PYTHON` permettent de choisir les exécutables.

## Stockage et limites des données

Les migrations additives v3 (qualité), v4 (multiples), v5 (scénarios) et v6 (cibles) suivent les migrations existantes. Leurs tables sont indépendantes des instantanés de portefeuille réécrits lors d’une sauvegarde. Une sauvegarde JSON du portefeuille n’est pas une sauvegarde de ces tables ; sauvegarder le fichier SQLite conserve l’ensemble.

L’historique du score et celui des multiples commencent aux captures effectivement réalisées. Les médianes de fenêtres de trois, cinq ou dix ans affichent le nombre réel d’observations et ne promettent pas cette durée de couverture. Les fondamentaux dont la disponibilité ou la devise historique ne sont pas vérifiées ne servent pas à reconstruire des valorisations passées. Les quatre multiples dérivés de FCF/EBIT sont calculables avec des trimestres TTM vérifiés ; les données Yahoo actuelles ne garantissent pas ces preuves. Les tests ne garantissent pas la disponibilité du service Yahoo en direct.

Les pairs sont uniquement des entreprises consultées avec même secteur exact, méthode et pondérations. Les méthodes industrielles ne sont pas forcées sur banques, assurances et REIT ; les mesures sectorielles spécialisées non fournies, telles que FFO/AFFO, restent indisponibles. Les rachats sont évalués par la réduction nette des actions dans une année de rachats déclarés, sans prétendre juger le prix payé. Le rendement incrémental du capital est descriptif et sensible aux acquisitions.

Les scénarios et valorisations avancées sont des simulations. Les estimations relatives nécessitent une saisie sourcée ; la pertinence de la synthèse et ses poids sont explicites. Les poids de synthèse restent dans la session ; les poids de qualité, scénarios et cibles sont persistés. Les valeurs futures supposent notamment dette et actions constantes. Le simulateur ne réutilise cibles et scénarios actuels qu’à la date présente, et son rendement de prix exclut frais et dividendes. Il ne crée aucune transaction.

## Ordre de revue

Les huit PR sont proposées en brouillon avec une base dépendante : ratios → fiche entreprise → qualité → valorisation historique → scénarios → analyses avancées → cibles → renforcement. Les numéros de lots 06–13 sont distincts des numéros GitHub. La dernière branche contient la validation combinée et ce bilan. Fusionner les dépendances dans cet ordre, en conservant leur contenu dans les suivantes.
