# PR 01 — Persister les historiques quotidiens sans purger les données existantes

## Objectif et périmètre

Sur `origin/main` `50a0e64`, un nouvel onglet retélécharge tout l'historique Yahoo et une migration supprime les observations SQLite existantes. Cette PR conserve les cours et taux sur le serveur, les réutilise après rechargement ou redémarrage et garde les anciennes observations lors d'un échec du fournisseur. Elle implémente **uniquement l'étape 0.1** de la phase 2, avec ses tests et une première validation navigateur. Le découpage des étapes restantes est dans [phase-2-plan.md](phase-2-plan.md).

## Fichiers impactés

| Fichiers | Modification |
|---|---|
| `history_store.py` | Migration v1, import des taux historiques, observations et provenance, politique de fraîcheur, récupération incrémentale, relecture complète, détection de lacunes et secours en panne |
| `server.py` | Retrait de la purge, migration atomique, API branchées sur SQLite, sauvegarde des portefeuilles indépendante du cache, import des anciens taux transmis par une sauvegarde |
| `market.py` | Paramètres `start` / `end` pour les téléchargements quotidiens incrémentaux ; intraday inchangé |
| `src/session-market.js` | Cache mémoire limité dans le temps, déduplication des requêtes simultanées, actualisation explicite et conservation des valeurs si le réseau échoue |
| `src/performance-ui.js`, `src/dashboard.js`, `src/app.js` | Textes français, sources/dates/couverture/avertissements visibles, actualisation des cours et du change, recalcul de la valorisation quand les taux sont corrigés ; anciens taux JSON transmis au serveur |
| `tests/test_history_store.py`, `tests/test_market.py`, `tests/test_server.py`, `tests/session-market.test.js` | Tests métier, migrations, fournisseur et API ; les deux anciens tests exigeant la destruction du cache sont remplacés par des tests de conservation |
| `scripts/check-history-browser.mjs`, `tests/browser_history_fixture.py` | Parcours Chromium reproductible, fournisseur simulé explicite, actif `FIXTURE` et base jetable isolée ; aucun contact avec une base utilisateur ni avec Yahoo |
| `package.json`, `package-lock.json`, `.gitignore` | Commande navigateur et dépendance de développement `playwright-core`, sans téléchargement automatique d'un navigateur |
| `README.md`, `docs/` | Contrat, politique, limites, audit et plan des PR |

## Migration v1 et conservation

La migration `durable_history_v1` est enregistrée dans `schema_migrations(version, name, applied_at)`. La création des tables et la normalisation s'exécutent dans une transaction SQLite avec verrou d'écriture pris avant l'inspection des marqueurs, pour éviter deux migrations simultanées.

- `prices` est réutilisée sans purge. Clé existante : `(ticker, date, provider)` ; prix, devise, source et date de récupération conservés.
- `fx_observations` ajoute la provenance à la clé `(source_currency, target_currency, date, provider)`, conserve aussi le payload utile et autorise une date de récupération inconnue pour les taux anciens.
- `history_fetches` conserve les dates de tentative, de succès, de relecture complète et la dernière erreur, par type/série/fournisseur. Une erreur ne remplace jamais la date du dernier succès.
- Les anciens taux de `fx_rates` et du payload `state.fxRates` sont copiés sans effacer leur origine. Les entrées non normalisables restent dans leur stockage original ; aucune devise, source ou date manquante n'est inventée.
- Le payload, les champs inconnus, la révision d'état, les portefeuilles et les transactions ne sont pas réécrits par cette migration. Les sauvegardes suivantes restent contrôlées par la révision habituelle.
- L'ancien marqueur `ephemeral_history_v1` est conservé ou neutralisé par une valeur de remplacement, afin qu'une réouverture de l'ancienne version ne déclenche pas sa purge initiale. Aucune table historique n'est supprimée lors d'une sauvegarde de portefeuille.

Une récupération valide peut corriger les valeurs du **même** fournisseur à une date déjà stockée ; les observations d'autres fournisseurs restent en base. L'API choisit une observation par date, en privilégiant le fournisseur actif et en exposant la source de chaque valeur. Cette PR ne constitue pas un journal de toutes les révisions historiques d'un fournisseur.

Retour arrière : arrêter le serveur et garder une sauvegarde SQLite. Ne pas supprimer `prices`, `fx_observations` ou les anciens payloads. Les tables additives peuvent rester inutilisées par l'ancienne version ; son API ne saura pas lire le nouveau cache FX. Revenir au code précédent ne restaure pas les données que cette ancienne version avait déjà effacées. Aucun script de retour arrière destructif n'est exécuté.

## Contrat et politique

Les API existantes gardent `data: [...]`. Chaque observation contient `source` et `fetchedAt`. Le champ additionnel `cache` contient :

- `status` (`fresh` ou `stale`), `lastAttemptAt`, `lastSuccessAt`, `lastFullAt`, `expiresAt`, `warning` ;
- `sources`, `firstDate`, `lastDate`, `observations` ;
- `missingWeekdaysCount` et les 100 premières dates ouvrées sans observation.

Le premier chargement récupère la couverture complète disponible chez Yahoo. Une récupération réussie est réutilisée pendant 24 h. Ensuite, la reprise couvre les sept jours précédant la dernière observation du fournisseur et les jours suivants. Tous les 30 jours, ou avec `full=1`, une relecture complète recherche les corrections et trous plus anciens. `refresh=1` contourne le délai de fraîcheur. Une relecture complète ne supprime pas les dates absentes de la nouvelle réponse.

Les réponses du fournisseur sont vérifiées intégralement avant écriture : identifiant, paire de devises, devise, dates réelles non futures, valeurs finies strictement positives, absence de doublons et tableau non vide. Une réponse invalide laisse les anciennes observations intactes.

En panne, une série déjà stockée reste disponible avec HTTP 200, `status=stale` et un avertissement visible ; une série jamais obtenue retourne HTTP 503. Un échec est conservé et les tentatives automatiques attendent cinq minutes. Une actualisation explicite permet une tentative immédiate. Les requêtes ordinaires concurrentes pour une même série partagent le résultat du premier téléchargement.

## Validation

Référence avant modification : **20 tests JS et 13 tests Python réussis** après installation des dépendances verrouillées du projet. Le Python système seul ne contenait pas `yfinance` ; les vérifications utilisent donc `.venv`.

```bash
npm ci
npm test
ATLAS_DB=/chemin/jetable/atlas-tests.sqlite3 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
npm run test:browser
git diff --check
```

Le test navigateur utilise Chromium installé à `/usr/bin/chromium`. Les chemins peuvent être adaptés avec `ATLAS_CHROMIUM` et `ATLAS_PYTHON`. Aucun navigateur n'est installé silencieusement. Les autres tests n'en ont pas besoin.

Résultats de la livraison : **25 tests JS**, **29 tests Python**, et **un parcours navigateur complet** réussis. Aucun test échoué restant. Couverture des cas : migration ancienne et post-drapeau éphémère, idempotence, rollback transactionnel sur erreur, provenance/date inconnue, rechargement/nouvelle instance, expiration, chevauchement incrémental, corrections, relecture complète sans purge, concurrence, panne avec/sans cache, délai de nouvelle tentative, réponse invalide atomique, lacunes sans remplissage, API HTTP 200/400/503, sauvegarde/révision/conflit et parcours UI.

Le parcours navigateur vérifie le rechargement, un nouvel onglet, un véritable redémarrage du processus serveur sans téléchargement supplémentaire, la correction d'un taux et de la valorisation affichée, les pannes des deux fournisseurs simulés avec avertissements et courbe conservée, le bouton Settings et l'ajout d'une transaction sans purge des historiques.

Vérification réseau réelle le 16 novembre 2026, dans une base de contrôle distincte : IBM, **16 327 observations**, du **1962-01-02 au 2026-11-13** ; USD/EUR, **5 957 observations**, du **2003-12-01 au 2026-11-16**. Ces tailles décrivent la réponse Yahoo obtenue lors du contrôle et ne garantissent pas une disponibilité future. Des avertissements de dépréciation pandas/yfinance ont été émis sans empêcher les récupérations.

## Bilan et limites

**Implémenté :** conservation quotidienne SQLite, migration non destructive, provenance, couverture et avertissements visibles, cache avec expiration, actualisation incrémentale et complète, secours fournisseur, tests métier/API/UI. Aucune base personnelle existante n'a été ouverte pour les essais ; uniquement des bases de tests et de contrôle dédiées.

**Partiel :** la détection de jours ouvrés sans observation ne connaît pas les calendriers de bourse. Les jours fériés restent des lacunes possibles, pas des erreurs certaines ; les trous anciens sont recherchés lors de la relecture complète. Le statut de fraîcheur décrit la récupération auprès du fournisseur, pas la complétude de sa réponse.

**Limites connues :** données déjà supprimées par une ancienne version irrécupérables sans sauvegarde/source ; historique dépendant de Yahoo ; monnaies non ISO comme GBp non normalisées ; clôture du jour potentiellement provisoire ; pas de traitement nouveau des splits/dividendes ; intraday 1D toujours en direct ; exports JSON des portefeuilles sans export complet des séries SQLite ; pas de journal de chaque correction ni nouveau connecteur fondamental. Les calendriers, périodes supplémentaires, TWR/XIRR étendus, nouveaux benchmarks, diversification, fondamentaux et scénarios restent dans les PR suivantes.

**Suite recommandée après validation :** PR 02 sur les périodes et les cas limites des performances, puis PR 03 sur les benchmarks. Ne pas fusionner automatiquement cette PR ni développer les étapes avancées avant le bilan P0.
