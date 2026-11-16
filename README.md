# Atlas — espace d’investissement

Prototype personnel en français. Il nécessite Python 3.12, Node.js et un accès réseau à Yahoo Finance. Depuis le dossier du projet, installez les dépendances puis démarrez le serveur :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm start
```

Ouvrez ensuite `http://localhost:8000`. Si un ancien serveur tourne déjà, arrêtez-le avec Ctrl+C avant de le relancer. Les commandes ci-dessus ciblent Linux et macOS ; sur Windows, utilisez les exécutables du dossier `.venv\Scripts` pour créer et lancer l'environnement virtuel.

## Données et sauvegardes

La base SQLite est créée sur la machine du serveur dans `~/.atlas-investment/atlas.sqlite3` (chemin personnalisable avec `ATLAS_DB`). Elle survit au redémarrage du serveur, mais pas nécessairement à la suppression ou au remplacement de la machine cloud : utilisez régulièrement **Settings → Exporter les données JSON** et conservez le fichier en lieu sûr. **Restaurer une sauvegarde** remplace les données actuelles après validation et confirmation. Le serveur écoute uniquement sur l'interface locale et ne propose pas d'authentification ; il est destiné à un usage personnel local.

Au premier démarrage avec une base vide, les données `atlas-v1` de l'ancien navigateur sont copiées dans SQLite, sans supprimer la copie d'origine. Ouvrez l'application dans ce même navigateur pour effectuer la migration. Si la base contient déjà des données, aucune migration automatique ne les écrase. Les révisions SQLite empêchent qu'un onglet ancien écrase silencieusement les modifications d'un autre onglet ; rechargez si un conflit est signalé. Les historiques et les portefeuilles utilisent une base commune : l’application ne fournit pas encore de comptes ou d’isolation entre utilisateurs.

Les entreprises, cours et transactions initiaux sont fictifs. La recherche utilise Yahoo Finance via yfinance lorsque l’accès réseau est disponible. Ne pas utiliser ce prototype comme registre financier officiel.

## Architecture et limites

`server.py` fournit l'API locale et la persistance SQLite ; `src/app.js` orchestre l'interface, les pages sont séparées dans `src/dashboard.js`, `src/portfolios.js`, `src/research.js` et `src/watchlist.js`, `src/csv.js` analyse le CSV, `src/valuation-ui.js` gère la simulation et `src/finance.js` centralise les calculs. L'état JSON existant est migré vers des tables de portefeuilles, transactions, instruments, fondamentaux et watchlist. Les historiques quotidiens de cours et de change sont conservés dans SQLite avec leur source et leur date de récupération, et relus au rechargement ou dans un nouvel onglet. La migration versionnée est additive : elle conserve les cours, les anciennes tables, les taux du JSON existant et les données de portefeuille. Les données déjà supprimées par une ancienne version ne peuvent être récupérées que depuis une sauvegarde ou le fournisseur. Les exports JSON de portefeuilles n'incluent pas ces historiques ; sauvegardez aussi la base SQLite. Les données de portefeuille et les dernières fiches consultées restent sauvegardées. Les positions sont reconstruites depuis les transactions. Les achats incluent les frais dans le coût ; les ventes utilisent le coût moyen pondéré et déduisent leurs frais du gain réalisé, y compris après clôture d'une position. Les portefeuilles ont pour devise de référence l'EUR ; les transactions peuvent être libellées dans une autre devise. Les cours et taux inconnus restent indisponibles. La plus-value affichée au tableau de bord est latente et ne représente pas un rendement global.

L'import accepte un CSV UTF-8 séparé par des virgules ou points-virgules, avec en-têtes et dates ISO. Les types sont `buy`, `sell`, `deposit`, `withdrawal`, `dividend`. Le mapping et un aperçu précèdent la validation ; les doublons exacts sont refusés. L'import est atomique.

## Données réelles et recherche

Yahoo Finance via `yfinance` ne demande aucune clé API pour ce parcours. Les données peuvent être différées, incomplètes ou temporairement indisponibles, et l'accès peut être limité par Yahoo. La bibliothèque n'est pas affiliée à Yahoo ; vérifiez les conditions d'utilisation du fournisseur, notamment avant tout usage autre que personnel.

Dans Research, cherchez une entreprise puis ouvrez un résultat ; la fiche récupère le profil et la dernière cotation. Source, date de cotation et date de récupération sont affichées, et les données sont conservées dans la sauvegarde JSON. Elles ne se mettent pas à jour automatiquement. Les données issues de l’ancien fournisseur conservent leur source jusqu’à actualisation. Un échec de mise à jour conserve la dernière donnée connue avec sa date. Les cotations étrangères sont converties en EUR au dernier taux disponible à la date du cours. Les transactions utilisent le dernier taux disponible à leur date, frais compris. Dans Settings, actualisez les historiques de change après avoir saisi les transactions et recherché les titres ; l'accès aux historiques Yahoo Finance peut être limité ou indisponible. Sans taux antérieur, la valeur correspondante est indisponible. Les anciennes transactions sans devise sont supposées en EUR. Les portefeuilles existants conservent leur calcul historique de trésorerie, qui suppose la conversion immédiate des flux en EUR. Lors de la création d’un portefeuille, le mode « soldes par devise » conserve chaque solde dans sa devise ; utilisez une transaction Change pour enregistrer les montants réellement débités et reçus. Les soldes négatifs sont possibles et doivent être rapprochés du courtier. Les montants sont convertis en EUR à la date de valorisation. Le portefeuille de démonstration conserve ses cours fictifs.

Les ratios proviennent du profil du fournisseur et peuvent être absents ou porter sur des périodes différentes. Le DCF est une simulation manuelle sur cinq flux annuels configurables : le FCFF s'actualise au WACC et déduit la dette nette ; le FCFE s'actualise au coût des fonds propres sans déduire à nouveau la dette. Les flux, la dette et le nombre d'actions doivent utiliser des unités cohérentes. Il ne constitue pas une recommandation ni une prévision. Les scores de qualité et d'opportunité, les fondamentaux historiques, les scénarios multiples, les opérations sur titres et l'authentification restent à réaliser.

Tests : `npm test` et `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.

## Historique et performance

Sur le tableau de bord, choisissez une période et un indice, puis cliquez sur **Actualiser les historiques**. Les cours de clôture et les taux Yahoo sont chargés à la demande puis conservés dans SQLite ; vous pouvez les actualiser explicitement. La source, la couverture réellement disponible, la date de récupération et les avertissements sont affichés sous le graphique. 1D interroge Yahoo Finance pour la dernière séance disponible en données intrajournalières espacées de cinq minutes, y compris le change ; les heures affichées utilisent le fuseau du navigateur. La variation commence au premier point commun disponible. Si une transaction est datée du jour de la séance, la courbe est indisponible car son heure n’est pas enregistrée. Des séances incompatibles ou des cotations trop anciennes empêchent également la valorisation. Les comparaisons utilisent le S&P 500 (^GSPC, indice de prix) et l'ETF URTH comme approximation du MSCI World : leurs prix sont convertis en EUR, sans dividendes réinvestis. Les comparaisons ne sont donc pas des indices de rendement total.

Le TWR relie les rendements quotidiens de la période sélectionnée en supposant les apports/retraits nets en fin de journée ; les achats, ventes, dividendes et changes restent internes au portefeuille. Les frais et dividendes influencent le rendement. Au premier financement, ainsi qu'après une période à zéro, le rapport entre la valeur finale et le financement inclut les frais et variations de cette journée. Un retrait total ne constitue pas une perte ; une perte réelle de 100 % reste dans le chaînage depuis l'origine après réinvestissement. Un trou de données n'est jamais traversé par un rendement reconstitué : le TWR depuis l'origine reste indisponible, mais une période ultérieure entièrement documentée peut être calculée. Le XIRR annualisé depuis l'origine utilise seulement les apports, retraits et la valeur finale en EUR, en ACT/365 ; il ne change pas avec la sélection de période et peut rester disponible si seuls des cours intermédiaires manquent. Il est indisponible si les flux ou la valeur finale manquent, si des racines multiples sont détectées ou si aucune solution unique ne peut être certifiée numériquement. Ces résultats dépendent de l'exhaustivité des transactions et des cours/taux. Un cours ou taux datant de plus de sept jours n'est pas reporté. Les fractions de journée, frais de conversion non saisis, opérations sur titres et fractionnements ne sont pas reconstruits automatiquement : vérifiez leur traitement avant d'interpréter les performances.


## Cache historique durable — première PR de la phase 2

L'audit de référence et le découpage des 13 PR sont dans [docs/phase-2-plan.md](docs/phase-2-plan.md). Le contrat et le bilan de cette première PR sont dans [docs/pr-01-history.md](docs/pr-01-history.md). Les fonctions fondamentales avancées restent à réaliser dans les PR suivantes.

- Fraîcheur : 24 heures après une récupération réussie. Le cache mémoire du navigateur respecte cette expiration et ne remplace pas SQLite.
- Actualisation incrémentale : reprise sept jours avant la dernière observation du fournisseur, avec upsert par date et source. Un historique complet est relu au premier chargement, tous les 30 jours, ou explicitement avec `full=1` pour rechercher les trous et corrections plus anciens. Aucune actualisation ne supprime les anciennes observations.
- Échec fournisseur : retour des dernières observations conservées avec `cache.status=stale` et un avertissement ; sans observation, HTTP 503. Nouvelle tentative automatique après cinq minutes, ou immédiatement sur actualisation explicite.
- Lacunes : dates ouvrées sans observation signalées, sans remplissage fictif. Elles peuvent correspondre à des jours fériés ; aucun calendrier de bourse n'est encore intégré. La date du jour est exclue de ce diagnostic car la séance peut être en cours.
- Les données intrajournalières 1D restent en direct et ne sont pas persistées par cette PR. Les clôtures sont des prix, sans réinvestissement des dividendes ni reconstruction des opérations sur titres.

Les API `GET /api/market/history?symbol=IBM` et `GET /api/market/fx?from=USD&to=EUR` conservent leur tableau `data` et ajoutent `cache`. `refresh=1` force une récupération incrémentale ; `full=1` force une relecture complète sans purge. Source et date de récupération figurent aussi dans chaque observation. Un ancien taux sans date de récupération conserve une date inconnue.

Avant une mise à jour sur votre installation, sauvegardez le fichier indiqué par `ATLAS_DB` (ou le chemin par défaut) avec l'API SQLite `Connection.backup`, ou copiez le fichier après arrêt du serveur. Gardez cette copie hors du dépôt. Les tests utilisent exclusivement des bases temporaires. Un retour arrière du code ne doit pas supprimer les tables historiques : voir les précautions dans le document de PR.


## Performances fiables — deuxième PR de la phase 2

Les dix périodes sont disponibles : **1D, 1W, 1M, 3M, 6M, YTD, 1Y, 3Y, 5Y, MAX**. Les mois et années utilisent des bornes calendaires UTC avec gestion des fins de mois et années bissextiles. YTD prend la clôture du 31 décembre comme référence pour inclure le premier janvier. La couverture réellement calculée est indiquée ; choisir 5Y ne crée pas cinq ans de données.

Les reports d'observations antérieures sont datés et signalés sous la courbe ; aucun cours de transaction ni taux futur ne remplace une observation absente. Les extrémités manquantes de la période restent visibles et rendent le rendement indisponible. Les calculs ne modifient pas les transactions. Le simulateur DCF et les données SQLite ne sont pas migrés par cette PR.

Les détails des formules, cas limites, fichiers, tests et limites sont dans [docs/pr-02-performance.md](docs/pr-02-performance.md). Pour les tests navigateur : `npm ci`, puis `npm run test:browser` avec Chromium installé (chemins personnalisables comme indiqué dans PR 01). La suite Python inclut désormais une comparaison indépendante du XIRR JavaScript avec les racines polynomiales NumPy pour 200 séries de flux annuels ; Node.js doit donc être disponible pour cette suite aussi.
