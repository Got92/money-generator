# PR 05 — historiques fondamentaux

La migration SQLite v2 ajoute `fundamental_instruments`, `fundamental_observations` et `fundamental_fetches`. Elle est transactionnelle, idempotente et ne touche pas aux tables de portefeuilles, aux snapshots `fundamentals`, aux prix ou au change. Sauvegarder la base SQLite avant mise à jour ; l'export JSON de l'application ne sauvegarde pas ces historiques. Aucun retour arrière automatique ne supprime les observations.

`GET /api/fundamentals/history?symbol=IBM&period=annual` accepte `period=annual|quarterly`, `refresh=1` et `asOf=AAAA-MM-JJ`. La première consultation charge le fournisseur ; les suivantes utilisent les données conservées jusqu'à actualisation explicite. `fetch.error` signale l'échec, même lorsque des valeurs antérieures restent disponibles. Une réponse vide peut être due à l'absence de données ou à une erreur : consulter `fetch.error`. La couverture liste les fins de période réellement présentes et les indicateurs disponibles ou manquants pour chacune, sans garantie de continuité ni de dix ans. La fiche entreprise permet de charger, actualiser et exporter le résultat JSON.

Le fournisseur est interchangeable via `FundamentalProvider`. Seul Yahoo Finance via yfinance est activé : aucune clé ni source authentifiée n'est introduite. Les données financières sont retournées avec la devise financière déclarée par Yahoo, ou une devise inconnue ; la provenance indique que cette métadonnée actuelle est appliquée aux périodes passées sans confirmation historique. Les changements de devise ne sont pas détectés et la comparabilité des périodes n'est pas garantie. Les actions diluées sont exprimées en nombre d'actions. Les métriques manquantes restent absentes. Les données sont les lignes publiées par Yahoo : aucun calcul de remplacement de FCF, dette nette ou fonds de roulement n'est effectué. Pour capex (`Capital Expenditure`), dividendes (`Cash Dividends Paid`) et rachats (`Repurchase Of Capital Stock`), le signe brut Yahoo est conservé : un décaissement est généralement négatif et un montant positif ne doit pas être automatiquement transformé en décaissement. Les autres signes sont eux aussi conservés. Chaque valeur conserve ligne brute, source, statut et date de récupération.

Chaque changement d'une observation d'une source crée une révision ; une répétition identique est dédupliquée. La réponse ordinaire présente la dernière révision par source, indicateur et période ; les révisions précédentes restent dans SQLite. Une donnée absente à l'actualisation ne supprime pas les valeurs précédentes. Les fins de période Yahoo ne sont pas des dates de publication : pour ce fournisseur, année et trimestre fiscaux et dates de publication/disponibilité restent inconnus. Les requêtes `asOf` n'incluent que les observations avec date de disponibilité connue et au plus égale à la date demandée, date de publication non postérieure si connue, et première récupération de cette révision au plus tard à cette date. Cette règle conservatrice exclut les historiques Yahoo actuels et peut aussi exclure des données pourtant publiées auparavant mais récupérées plus tard. Elle empêche d'utiliser une révision ultérieure comme si elle était connue dans le passé.

Yahoo peut limiter la profondeur, la disponibilité ou les champs ; aucun historique ni date de publication n'est inventé. Des données Yahoo partiellement manquantes ne doivent pas être interprétées comme des zéros ; l'identité par symbole est stable dans la base mais ne résout pas les changements de ticker ou collisions entre places boursières. Les analyses de ratios, scores et graphiques relèvent des PR suivantes.


## Fichiers et intégration

La PR 05 est intégrée sur PR 04 après le [bilan P0 combiné](p0-validation.md), lui-même effectué sur PR 03. Les conflits dans les modules statiques, l'orchestration et les scripts de test ont été résolus en conservant les fonctionnalités des trois PR. `main` n'est pas modifiée par ces nouvelles branches.

| Fichiers | Modification |
|---|---|
| `fundamental_provider.py` | Interface de fournisseur, adaptateur Yahoo annuel/trimestriel, métriques et unités normalisées, signes conservés, booléens et valeurs non financières rejetés, devise courante identifiée comme non vérifiée historiquement |
| `fundamental_store.py` | Migration v2 additive, instruments identifiés, observations brutes et normalisées révisables, déduplication, couverture et champs absents par période, filtrage historique conservateur |
| `server.py` | Application transactionnelle de la migration et API d'historiques ; modules statiques existants préservés |
| `src/fundamental-ui.js`, `src/research.js`, `src/app.js` | Consultation française, chargement/erreur/vide, export JSON réel, avertissements de devise et métriques manquantes ; absence de chargement réel pour une entreprise fictive de démonstration sans profil réel |
| `tests/test_fundamentals.py`, `tests/test_server.py`, `tests/test_history_store.py` | Fournisseur, périodes, métadonnées, révisions, dates, absence d'anticipation, réponses invalides, migration et conservation de l'état/prix/change/snapshots lors des sauvegardes |
| `scripts/check-fundamentals-browser.mjs`, `package.json` | Navigation réelle jusqu'à la fiche depuis la watchlist, séparation démo, JSON téléchargé et relu, annuel/trimestriel, données manquantes et erreur sur base jetable ; ajout aux deux parcours navigateur existants |

## Validation finale cumulée

- **73 tests JavaScript**, **40 tests Python**, aucun échec restant. La suite Python inclut le contrôle indépendant XIRR sur 200 registres.
- **Trois parcours Chromium réussis** : historique/performance/benchmarks (ordinateur et mobile), diversification, et fiche entreprise avec états financiers et téléchargement JSON.
- `git diff --check` et vérification syntaxique des modules modifiés réussis.
- Tests réseau réels isolés : IBM annuel, **80 observations**, fins de période du **2022-12-31 au 2025-12-31** ; IBM trimestriel, **100 observations**, fins de période du **2025-09-30 au 2026-09-30**. Ces couvertures décrivent la réponse obtenue, pas une garantie de continuité future. Les observations manquantes sont indiquées par la couverture.

Commandes reproductibles depuis le dépôt, après installation des dépendances et de Chromium :

```bash
npm test
ATLAS_DB=/chemin/jetable/atlas-tests.sqlite3 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
npm run test:browser
git diff --check
```

`ATLAS_PYTHON` et `ATLAS_CHROMIUM` permettent d'adapter le parcours navigateur. Les répertoires temporaires suivent `TMPDIR` si défini ; les tests n'ouvrent jamais la base personnelle. Les données synthétiques du navigateur sont étiquetées comme fixtures et ne sont pas ajoutées aux analyses réelles.

Le moteur et l'API sont opérationnels pour les données effectivement disponibles. La date de publication/ disponibilité et les identifiants fiscaux Yahoo restent inconnus ; ces données sont exclues de l'analyse historique `asOf`. La devise des périodes passées n'est pas confirmée par une métadonnée actuelle : la provenance et l'interface le signalent. Les ratios, graphiques fondamentaux complets, scores et valorisations historiques restent dans PR 06 et suivantes.
