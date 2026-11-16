# Atlas — audit et découpage de la phase 2

## Révision et méthode

Audit initial sur `origin/main` **50a0e64c72f787b5d92a42aefa350a0b4835fd6b**. Le 16 novembre 2026, les PR 01 et 02 sont confirmées fusionnées dans `origin/main` **b18d3e09d2d56f7c2c8c6ee65a09faf36eb8d4ad**. À la demande de l'utilisateur, un sous-agent Terra 6.1 High est chargé de chacune des PR 03, 04 et 05 dans des worktrees isolés. L'intégration est séquentielle : PR 03, PR 04 et bilan P0 combiné, puis PR 05. Les nouvelles PR restent sur des branches dédiées, sans fusion automatique. Voir [bilan P0](p0-validation.md).

## Comparaison au code lors de l’audit initial (50a0e64)

| Besoin | État observé | Dépendances / écart |
|---|---|---|
| Portefeuilles, transactions, PRU, CSV | Présents : `server.py`, `finance.js`, `csv.js`, `portfolios.js` | Révision optimiste de l'état ; calcul des positions depuis les transactions ; préserver les champs JSON inconnus et les transactions |
| Stockage | SQLite : `state`, `portfolios`, `transactions`, `instruments`, `fundamentals`, `watchlists`, `prices`, `fx_rates`, `schema_meta` | La normalisation est marquée par un drapeau, sans registre de migrations versionnées |
| Cours / change quotidiens | Fournisseur réel dans `market.py`, cache mémoire dans `session-market.js` | **P0 :** migration `ephemeral_history_v1` efface `prices`, `fx_rates` et les taux du JSON ; `write_collections` efface encore `fx_rates` à chaque sauvegarde ; téléchargements complets à chaque nouvel onglet |
| Performance | `performance.js`, `performance-ui.js`, `intraday.js` | TWR quotidien, XIRR, cinq périodes (1D, 1W, 1M, YTD, MAX), 1D intrajournalier réel ; tests encore limités pour zéro, trous, liquidation et flux multiples |
| Benchmarks | S&P 500 `^GSPC`, proxy MSCI World `URTH` | Prix seulement, conversion EUR et début commun partiels ; pas de registre extensible ni sélection TR/PR, fin commune à fiabiliser |
| Diversification | Secteur et pays, calcul sur le capital investi | Industrie disponible dans le profil mais pas affichée ; devises, classes d'actifs et base avec cash absentes |
| Recherche entreprise | Profil Yahoo, cours daté, industrie, pays, quelques ratios fournisseur | Snapshot JSON dans `instruments` / `fundamentals`, pas d'états financiers annuels / trimestriels ; la table `fundamentals` ne constitue pas un historique |
| DCF | `valuation.js` + `valuation-ui.js` | FCFF/WACC et FCFE/coût des fonds propres, cinq flux manuels ; conserver ce moteur ; scénarios sauvegardés, reverse DCF et sensibilités absents |
| Score / valorisation historique | Non implémentés | Nécessitent états financiers, provenance, disponibilités de publication, unités, méthodes sectorielles et cours persistants |
| Cibles / renforcement | Non implémentés | Nécessitent allocation fiable, moteur `finance.js` et devises ; ne jamais écrire une simulation dans les transactions |
| Tests | Node natif et Python unittest | Référence initiale : 20 tests JS réussis ; lancement Python système bloqué par `yfinance` absent, environnement à installer avant validation |

## Contrats transversaux

Séparer les observations du fournisseur, leurs révisions, les calculs et les hypothèses de simulation. Un champ absent reste indisponible. Les ratios ne mélangent jamais devises, unités, trimestre isolé, TTM et forward. Une analyse historique filtre sur une date de disponibilité identifiable ; à défaut, elle indique que l'usage historique est impossible. Les tests utilisent des fixtures identifiées, jamais des données de démonstration affichées comme des données réelles. Aucun nouveau fournisseur authentifié n'est activé implicitement.

## Pull Requests proposées

Chaque ligne est une PR avec code, tests, limites et bilan. Les numéros désignent l'ordre de livraison, pas des PR GitHub déjà créées.

| PR | Objectif et fichiers principaux | Migration | Validation / dépendances |
|---|---|---|---|
| **01 — Historiques durables (fusionnée)** | `history_store.py`, `server.py`, `market.py`, `session-market.js`, textes des pages, tests, documentation : conserver l'existant, cache SQLite, provenance, actualisation incrémentale, secours en panne et couverture | v1 additive : registre `schema_migrations`, observations FX par fournisseur et métadonnées de récupération ; réutiliser `prices`, importer les anciens taux sans supprimer leur source | Migration pré/post-drapeau éphémère, idempotence, sauvegarde sans purge, rechargement, chevauchement, déduplication, échec fournisseur, requêtes concurrentes, métadonnées visibles |
| 02 — Performances fiables (fusionnée) | `performance.js`, `finance.js`, `intraday.js`, `performance-ui.js`, tests : toutes les périodes, bornes calendaires, TWR/XIRR et données manquantes | Aucune prévue ; ne pas changer l'heure des flux existants | Dépôts/retraits, frais, dividendes, achats/ventes, liquidation, valeur zéro puis réinvestissement, change, week-ends, trous, XIRR ambigu ; dépend de 01 |
| 03 — Registre des benchmarks (implémentée et revue) | Nouveau `benchmarks.js`, adaptateurs marché, UI performance et tests : six indices, variantes PR/TR explicites et proxies signalés | Métadonnées des séries uniquement si nécessaires | Dates de début **et de fin** communes, change historique, absence de TR, série indisponible, absence de dividendes fictifs ; dépend de 01–02 |
| 04 — Diversification et bilan P0 (validation combinée réussie) | Nouveau module allocation, `dashboard.js`, page Analytics extraite de `app.js`, profil marché | Classe d'actif nullable dans le profil existant | Industrie, devise, pays, classe inconnue explicite ; dénominateurs investi / cash inclus, valeurs manquantes ; dépend de 01–02 ; passage de toutes les suites avant les modules avancés |
| 05 — Moteur fondamental historique (intégration après bilan P0) | Modules Python de fournisseurs et normalisation, API dédiée, stockage SQLite | v2 : instruments identifiés, périodes annuelles/trimestrielles, valeurs brutes et normalisées, unité/devise, publication/disponibilité nullable, source/révision/statut ; clés uniques sans écraser la provenance | Connecteur yfinance sans nouvelle clé ; couverture réelle, données manquantes, mises à jour, conservation des révisions, filtre historique anti-anticipation ; dépend du bilan P0 |
| 06 — Ratios fondamentaux réutilisables | Module métier indépendant + tests, définitions et contrats API | Pas de nouvelle table nécessaire | CAGR 3/5/10 ans réellement couverts, bases négatives, ROIC/ROE/ROA, marges, dette, conversion cash, dilution ; moyennes de bilans et dates cohérentes ; méthodes financières/REIT explicites ; dépend de 05 |
| 07 — Fiche entreprise et graphiques | `research.js` et modules de graphiques dédiés, API historique | Aucune | Annuel/trimestre/TTM, fenêtres 3/5/10 ans selon couverture, sources/dates/formules, chargement/erreur/vide, interactions ; dépend de 05–06 |
| 08 — Score de qualité explicable | Module Python de scoring indépendant, UI et radar, comparaison sectorielle | v3 : configuration de pondérations et versions méthodologiques ; scores historisés seulement avec provenance exploitable | Six dimensions 25/20/20/15/10/10 ; valeurs absentes exclues avec couverture, seuil minimal documenté, score indisponible sinon, finance/REIT adaptés ; FCF yield exclu de qualité pure ; dépend de 06–07 |
| 09 — Valorisation historique | Module des multiples, API/UI, médianes/percentiles et prix d'entrée | v4 : observations de valorisation datées avec références aux fondamentaux disponibles à cette date | Multiples TTM/forward séparés, numérateurs datés, pas d'historique inventé, percentiles et tailles d'échantillons, EV → fonds propres → prix/action ; dépend de 01 et 05–07 |
| 10 — Scénarios DCF persistants | Étendre `valuation.js` et `valuation-ui.js`, stockage d'hypothèses | v5 : scénarios par entreprise, devise, unité, méthode, cinq années et hypothèses, sans modifier les transactions | Bear/Base/Bull modifiables, dette FCFF seulement, marge de sécurité, valeur présente/future/rendement distincts et dividendes explicitement supposés ; dépend de 06–07 |
| 11 — Reverse DCF, sensibilités et synthèse | Modules métier de valorisation + UI | Configuration de pondérations dans les scénarios | Recherche de racine, absence de solution, WACC/g, croissance/marge, croissance/multiple, synthèse limitée aux méthodes pertinentes et comparables ; dépend de 09–10 |
| 12 — Allocations cibles | Module allocation, API et formulaires par portefeuille | v6 : cibles position/secteur/industrie, bornes et portefeuille propriétaire | Sommes et bornes, isolation des portefeuilles, écarts réels et alertes, cash explicite ; dépend de 04 |
| 13 — Simulateur de renforcement | Nouveau module utilisant `finance.js`, accès depuis position/entreprise | Aucune transaction réelle ; éventuellement hypothèses sauvegardées dans table dédiée après besoin confirmé | Cloner les transactions en mémoire, frais/PRU/change, quantité ou montant, cash restant, nouvelles pondérations, cibles et scénarios ; vérifier zéro écriture API ; dépend de 10–12 |

Les numéros de migration futurs sont indicatifs : chaque PR réservera le suivant après validation du schéma réel. Les nouvelles tables sont additives. Les retours arrière conservent les observations : pas de `DROP` automatique sur les historiques utilisateur. Une sauvegarde SQLite précède toute migration sur une installation personnelle ; les essais ici utilisent uniquement des bases temporaires.

## Périmètre exact de PR 01

Réutiliser les contrats de réponse `data` des deux API historiques et ajouter `cache` pour l'état de fraîcheur, les sources, les dates, les jours ouvrés sans observation et les avertissements. Garder l'intraday en direct. Durée de fraîcheur quotidienne : 24 h ; nouvelle tentative après panne : 5 min ; relecture complète tous les 30 jours ou explicitement, pour les trous et corrections anciennes. Une actualisation ordinaire recouvre les sept derniers jours et ajoute les observations manquantes ; elle ne supprime jamais les observations anciennes. Les jours fériés ne sont pas assimilés à des cours manquants certains. La couverture affichée n'est pas une promesse d'historique complet.

Préserver les tables et champs inconnus, les révisions de l'état et les dates/provenances existantes. Les timestamps inconnus des anciens taux restent inconnus. Les caches ne doivent plus être purgés par la sauvegarde des portefeuilles. Les exports JSON de portefeuilles ne sont pas une sauvegarde des historiques SQLite ; le document de PR doit le préciser.
