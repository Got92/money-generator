# PR 02 — Périodes et performances fiables

## Base et périmètre

Suite autorisée par l'utilisateur après livraison de PR 01. Celle-ci reste ouverte en brouillon : PR 02 part de son commit `695cf26` sur `codex/atlas-p0-performance` et cible `codex/atlas-p0-history-cache`. Le diff est ainsi limité à PR 02. Après fusion de PR 01, rebaser ou réorienter PR 02 vers `main`. Aucune fusion automatique et aucune migration SQLite dans cette PR.

## Constats et plan d'implémentation

- Les périodes 3M, 6M, 1Y, 3Y et 5Y manquent ; 1M utilise 30 jours plutôt qu'un mois calendaire et YTD oublie la clôture du 31 décembre. Ajouter des bornes UTC calendaires avec gestion des fins de mois et années bissextiles.
- Le TWR redémarre à 100 après certaines données absentes. Séparer la reconstruction du patrimoine, le rendement quotidien et le chaînage depuis l'origine. Un trou ne doit jamais être traversé par un rendement inventé ; un intervalle ultérieur entièrement documenté peut être calculé séparément.
- Une liquidation ou un retrait total fait tomber la valeur à zéro. Distinguer retrait du capital, perte totale, période sans capital et nouveau financement. Conserver une perte de 100 % dans le chaînage depuis l'origine.
- Le XIRR actuel ne trie/agrège/valide pas les flux et cherche uniquement des changements de signe sur une grille. Isoler les racines avec leurs points critiques ; refuser les racines multiples, tangentes non certifiables et résultats non représentables. Les cours intermédiaires ne sont pas nécessaires au XIRR si les flux et la valeur finale sont connus.
- Les devises natives d'un portefeuille multidevise peuvent être reconstruites même si un taux historique manque ; leur valeur EUR et la conversion des flux restent indisponibles aux dates concernées. Un achat ou change interne ne devient jamais un apport externe.
- L'interface doit utiliser la période réellement calculable, inclure les extrémités manquantes dans le diagnostic et expliquer les rendements indisponibles. Ne pas allonger `app.js`.

Fichiers prévus : `performance.js`, modules dédiés aux périodes et au XIRR, `performance-ui.js`, `intraday.js`, éventuel paramètre de fraîcheur dans `finance.js`, liste des modules servis dans `server.py`, tests métier et parcours navigateur, README et présent bilan. Les nouveaux indices et la refonte des benchmarks restent dans PR 03.

## Vérifications prévues

Conserver toutes les suites de PR 01. Ajouter des cas numériques indépendants couvrant dépôts/retraits, dividendes, frais, achats et ventes successifs, liquidation, zéro et réinvestissement, modes de cash, change historique absent/futur/périmé, cours manquants, report documenté des observations sur les jours sans cotation, périodes calendaires, XIRR nul/unique/multiple/tangent et interactions de sélection de période. Les bases et actifs de test restent isolés et explicitement synthétiques.

## Comportement livré et formules

Pour une clôture `V(t)`, un apport externe net `C(t)` et une valeur précédente strictement positive, le facteur journalier est `(V(t) − C(t)) / V(t−1)`. Le TWR est le produit des facteurs, moins un. Seuls les dépôts et retraits sont externes. Les mouvements de trésorerie, frais compris, réutilisent `cashBalances` de `finance.js` ; les quantités suivent le registre de transactions validé.

Au premier financement et à un redémarrage après zéro, le facteur est `V(t) / C(t)` si l'apport net est positif : cette convention inclut les frais et variations du jour de financement, dont l'heure reste inconnue. Si capital et flux sont tous deux nuls, le facteur neutre est un ; cela ne crée pas de rendement pour une période entièrement sans capital. Un retrait total conserve l'indice ; une vraie perte totale le multiplie par zéro et cet indice depuis l'origine ne ressuscite pas après un nouvel apport. Un sous-intervalle après recapitalisation peut néanmoins mesurer son propre rendement.

Une valorisation absente produit `value=null`, jamais un prix de transaction ou zéro par défaut. Le rendement quotidien est indisponible pour cette date et pour la première valorisation suivant la lacune, faute de base précédente. Le chaînage depuis l'origine reste alors indisponible. `periodPerformance` chaîne uniquement les facteurs dans la fenêtre sélectionnée à partir d'une base documentée ; une fenêtre ultérieure complète peut donc fonctionner. Les bords absents ne sont pas supprimés pour fabriquer un rendement jusqu'à la « dernière bonne date ».

Les observations reportées sont les derniers cours et taux réellement présents **à la date ou avant celle-ci**, au plus sept jours calendaires auparavant. Chaque point conserve `priceDates`, `fxDates` et `carried`. L'interface indique combien de dates utilisent de tels reports. Sans calendrier de bourse, elle ne garantit pas une nouvelle clôture pour chaque jour ouvré. Les devises natives et quantités continuent d'être reconstruites en mode multidevise quand un taux manque ; la valeur EUR et le flux externe concerné restent indisponibles. En mode de conversion immédiate, un taux de transaction absent laisse le cash converti inconnu.

Le XIRR résout `Σ flux(i)/(1+r)^((date(i)−date(0))/365) = 0` pour `r > −1`. Les flux de même date sont agrégés, triés et validés. L'évaluation en logarithmes évite les dépassements d'échelle. Les bornes sont calculées par domination des termes extrêmes ; les points critiques de la somme exponentielle partitionnent ses intervalles monotones. Cela détecte les racines multiples même proches, contrairement à l'ancienne grille de signes. Une tangence, une instabilité, une profondeur d'isolation supérieure à 128 ou un résultat non représentable donnent une valeur indisponible accompagnée d'une explication. Le calcul ne prétend pas choisir arbitrairement une racine économique parmi plusieurs solutions.

Le XIRR reste **depuis l'origine**, indépendamment du bouton de période. Il dépend des flux externes convertis et de la valorisation finale, et peut donc exister malgré des cours intermédiaires absents. Le sélectionner n'annualise pas le TWR de la fenêtre. Un benchmark ne change plus silencieusement la période du TWR du portefeuille.

Les mois et années sont soustraits dans le calendrier UTC avec écrêtage en fin de mois (31 mars → 29 février en 2024). YTD démarre au 31 décembre précédent. La fenêtre affiche sa couverture réelle plutôt qu'une durée promise. 1D reste une variation intrajournalière sur la dernière séance, sans modification rétroactive de l'heure des transactions.

## Fichiers effectivement impactés

| Fichiers | Rôle |
|---|---|
| `src/performance.js` | Reconstruction quotidienne, provenance des observations utilisées, flux et facteurs, indice depuis l'origine et XIRR séparés |
| `src/performance-periods.js` | Dix périodes, bornes calendaires, chaînage de la fenêtre et raisons d'indisponibilité |
| `src/xirr.js` | Calcul indépendant du frontend, validation et isolation des racines |
| `src/finance.js`, `src/intraday.js` | Paramètre optionnel d'âge maximal du change pour le cash converti intrajournalier ; tri et contrôle des observations, soldes nuls, positions liquidées, change positif et limite de 30 minutes |
| `src/performance-ui.js` | Dix boutons, vraies dates de fenêtre, résumé TWR/XIRR et erreurs, reports signalés ; chargement intraday limité aux positions ouvertes, réutilisation des séries déjà chargées pendant ce calcul |
| `server.py` | Autorisation de servir les deux nouveaux modules JavaScript ; aucun changement de schéma ni de stockage |
| `tests/performance-edge-cases.test.js`, `tests/performance-periods.test.js`, `tests/xirr.test.js`, `tests/intraday.test.js` | Cas numériques et régressions |
| `tests/test_xirr_reference.py` | Oracle indépendant NumPy pour 200 registres annuels déterministes, dates espacées de 365 jours |
| `tests/browser_history_fixture.py`, `scripts/check-history-browser.mjs` | Régression PR 01, dix périodes, lacune initiale puis période valide, fin indisponible, XIRR indépendant, benchmark, intraday et boutons accessibles sur mobile |
| `README.md`, `docs/phase-2-plan.md`, présent document | Méthode, résultats, dépendance de PR et limites |

`app.js` n'est pas agrandi. Les données financières de démonstration restent confinées aux tests isolés et aux données de démonstration existantes.

## Résultats de validation

Référence PR 01 confirmée avant modification : 25 tests JavaScript réussis. Résultats PR 02 : **63 tests JavaScript**, **30 tests Python** et **un parcours Chromium complet** réussis ; aucun échec restant. La trentième vérification Python compare 200 séries déterministes au polynôme indépendant obtenu avec `y = 1+r`, via `numpy.roots` : racine unique retrouvée, aucune racine multiple acceptée.

```bash
npm test
ATLAS_DB=/chemin/jetable/atlas-tests.sqlite3 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
npm run test:browser
git diff --check
```

Les suites préexistantes de persistance, API, transaction, change, DCF et recherche passent. Le navigateur réexécute le rechargement, nouvel onglet, redémarrage réel du serveur, corrections de change, panne fournisseur et sauvegarde sans purge de PR 01. Les vérifications supplémentaires couvrent les dix sélections de période, un TWR récent après une lacune ancienne, un XIRR encore disponible dans ce cas, le TWR inchangé quand on active le benchmark, la séance 1D, une extrémité finale manquante, les boutons à 390 px et l'absence de modification de la révision des transactions par les calculs. Tous les fournisseurs y sont simulés et tous les fichiers SQLite sont jetables.

## Bilan, limites et suite

**Implémenté :** dix périodes, bornes calendaires, TWR et XIRR testés sur les cas de flux et de devises, liquidations et zéro, reports explicites, lacunes sans redémarrage arbitraire, extrémités conservées et messages d'indisponibilité. Pas de migration ni de réécriture des transactions.

**Partiel / limites connues :** la convention journalière ne remplace pas des heures de flux réelles. Les opérations sur titres et calendriers de bourse ne sont pas reconstruits ; un fournisseur omettant un cours de titre sans valeur ne permet pas de le supposer égal à zéro. Le calcul 1D exige des données d'une même séance, refuse les transactions du jour sans heure et conserve la limite de 30 minutes pour les cours/taux ; un portefeuille uniquement en cash EUR n'a pas de courbe intrajournalière sans série de séance. Les valeurs nettes négatives ne donnent pas de TWR via cette méthode. Le XIRR peut être indisponible par prudence numérique ; l'annualisation d'une période courte peut produire un nombre élevé. Les courbes utilisent la dernière observation antérieure, explicitement signalée, dans leur limite de sept jours. Les six benchmarks et la distinction PR/TR restent à traiter dans PR 03.

**Prochaine action :** revoir PR 01 puis PR 02, fusionner dans l'ordre choisi par l'utilisateur, réorienter PR 02 vers `main` quand PR 01 y est intégrée ; poursuivre ensuite PR 03. Aucune de ces fusions n'est effectuée automatiquement.
