# Atlas — espace d’investissement

Prototype personnel en français. Lancez `npm start`, puis ouvrez `http://localhost:8000`. Il nécessite Python 3 et Node.js pour les tests ; aucune dépendance supplémentaire n'est requise. Si l'ancien serveur est déjà lancé, arrêtez-le avec Ctrl+C puis relancez la commande : l'ancien serveur statique ne fournit pas l'API SQLite.

## Données et sauvegardes

La base SQLite est créée sur la machine du serveur dans `~/.atlas-investment/atlas.sqlite3` (chemin personnalisable avec `ATLAS_DB`). Elle survit au redémarrage du serveur, mais pas nécessairement à la suppression ou au remplacement de la machine cloud : utilisez régulièrement **Settings → Exporter les données JSON** et conservez le fichier en lieu sûr. **Restaurer une sauvegarde** remplace les données actuelles après validation et confirmation. Le serveur écoute uniquement sur l'interface locale et ne propose pas d'authentification ; il est destiné à un usage personnel local.

Au premier démarrage avec une base vide, les données `atlas-v1` de l'ancien navigateur sont copiées dans SQLite, sans supprimer la copie d'origine. Ouvrez l'application dans ce même navigateur pour effectuer la migration. Si la base contient déjà des données, aucune migration automatique ne les écrase. Les révisions SQLite empêchent qu'un onglet ancien écrase silencieusement les modifications d'un autre onglet ; rechargez si un conflit est signalé.

Les entreprises, cours et transactions initiaux sont fictifs. Aucun fournisseur de marché réel n'est encore configuré. Ne pas utiliser ce prototype comme registre financier officiel.

## Architecture et limites

`server.py` fournit l'API locale et la persistance SQLite ; `src/app.js` contient l'interface et l'import CSV ; `src/finance.js` centralise les calculs ; `src/data.js` fournit le jeu fictif. La base stocke actuellement un état versionné et prépare une table de cours datés, qui n'est pas encore alimentée. Les positions sont reconstruites depuis les transactions. Les achats incluent les frais dans le coût ; les ventes utilisent le coût moyen pondéré et déduisent leurs frais du gain réalisé, y compris après clôture d'une position. Les calculs sont en EUR uniquement ; les cours inconnus restent indisponibles. La plus-value affichée au tableau de bord est latente et ne représente pas un rendement global.

L'import accepte un CSV UTF-8 séparé par des virgules ou points-virgules, avec en-têtes et dates ISO. Les types sont `buy`, `sell`, `deposit`, `withdrawal`, `dividend`. Le mapping et un aperçu précèdent la validation ; les doublons exacts sont refusés. L'import est atomique.

Le fournisseur réel, la recherche d'actifs, les historiques, TWR, benchmarks, fondamentaux et scénarios de valorisation restent à réaliser. L'accès réseau aux services de marché testés a été refusé par la politique réseau cloud ; les cours fictifs ne doivent pas être interprétés comme des cotations. La gestion multidevise, les opérations sur titres et l'authentification ne sont pas implémentées.

Tests : `npm test` et `python3 -m unittest discover -s tests -p 'test_*.py'`.
