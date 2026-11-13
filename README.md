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

Au premier démarrage avec une base vide, les données `atlas-v1` de l'ancien navigateur sont copiées dans SQLite, sans supprimer la copie d'origine. Ouvrez l'application dans ce même navigateur pour effectuer la migration. Si la base contient déjà des données, aucune migration automatique ne les écrase. Les révisions SQLite empêchent qu'un onglet ancien écrase silencieusement les modifications d'un autre onglet ; rechargez si un conflit est signalé.

Les entreprises, cours et transactions initiaux sont fictifs. La recherche utilise Yahoo Finance via la bibliothèque non officielle `yfinance`. Ne pas utiliser ce prototype comme registre financier officiel.

## Architecture et limites

`server.py` fournit l'API locale et la persistance SQLite ; `src/app.js` contient l'interface et l'import CSV ; `src/finance.js` centralise les calculs ; `src/data.js` fournit le jeu fictif. La base stocke actuellement un état versionné et prépare une table de cours datés, qui n'est pas encore alimentée. Les positions sont reconstruites depuis les transactions. Les achats incluent les frais dans le coût ; les ventes utilisent le coût moyen pondéré et déduisent leurs frais du gain réalisé, y compris après clôture d'une position. Les calculs sont en EUR uniquement ; les cours inconnus restent indisponibles. La plus-value affichée au tableau de bord est latente et ne représente pas un rendement global.

L'import accepte un CSV UTF-8 séparé par des virgules ou points-virgules, avec en-têtes et dates ISO. Les types sont `buy`, `sell`, `deposit`, `withdrawal`, `dividend`. Le mapping et un aperçu précèdent la validation ; les doublons exacts sont refusés. L'import est atomique.

## Données réelles et recherche

Yahoo Finance via `yfinance` ne demande aucune clé API pour ce parcours. Les données peuvent être différées, incomplètes ou temporairement indisponibles, et l'accès peut être limité par Yahoo. La bibliothèque n'est pas affiliée à Yahoo ; vérifiez les conditions d'utilisation du fournisseur, notamment avant tout usage autre que personnel.

Dans Research, cherchez une entreprise puis ouvrez un résultat ; la fiche récupère le profil et la dernière cotation. Source, date de cotation et date de récupération sont affichées, et les données sont conservées dans la sauvegarde JSON. Elles ne se mettent pas à jour automatiquement. Les données issues de l'ancien fournisseur conservent leur source d'origine jusqu'à une actualisation explicite. Un échec de mise à jour conserve la dernière donnée connue avec sa date. Les positions utilisent uniquement des cotations dont la devise indiquée par le fournisseur est EUR ; aucune conversion de change n'est effectuée. Le portefeuille de démonstration conserve ses cours fictifs.

Les ratios proviennent du profil du fournisseur et peuvent être absents ou porter sur des périodes différentes. Le DCF est une simulation manuelle sur 5 ans : FCF d'entreprise, croissance constante, valeur terminale, dette nette et actions selon les hypothèses saisies. Il ne constitue pas une recommandation ni une prévision. Les scores de qualité et d'opportunité, les fondamentaux historiques, les scénarios multiples, les historiques de performance et benchmarks restent à réaliser. La gestion multidevise, les opérations sur titres et l'authentification ne sont pas implémentées.

Tests : `npm test` et `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
