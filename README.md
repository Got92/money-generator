# Atlas — espace d’investissement

Prototype personnel en français. Lancer `npm start`, puis ouvrir l’application sur le port 8000. Tests : `npm test` (Node.js récent). Aucune installation de dépendances nécessaire.

Les entreprises, cours et transactions initiaux sont fictifs. Les données utilisateur sont stockées dans le navigateur (localStorage), sans compte, synchronisation ni sauvegarde serveur ; export JSON disponible dans Settings. Ne pas utiliser comme registre financier officiel.

## Architecture

`src/app.js` contient l’interface, la navigation et l’import CSV ; `src/finance.js` centralise les calculs ; `src/data.js` fournit le jeu fictif via un fournisseur interchangeable. Entités initiales : portefeuilles, transactions et watchlist. Les positions sont reconstruites chronologiquement depuis les transactions et les cours fournis. Le stockage local est un premier schéma, pas une base de données serveur. Une évolution devrait introduire des tables distinctes pour entreprises, instruments, comptes, transactions et cours datés, avec provenance et devise.

Les achats incluent les frais dans le coût ; les ventes utilisent le coût moyen pondéré et déduisent leurs frais du gain réalisé. Les transactions et calculs sont en EUR uniquement ; les prix inconnus restent indisponibles. La plus-value affichée est latente, sur les positions ouvertes, et ne représente pas un rendement global. Aucun historique, benchmark, rendement annualisé ou cours réel n’est inventé. Les modules non disponibles sont signalés.

L’import accepte un CSV UTF-8 séparé par des virgules, avec en-têtes et dates ISO. Les types sont `buy`, `sell`, `deposit`, `withdrawal`, `dividend`. Le mapping et un aperçu précèdent la validation ; les doublons exacts sont refusés. L’import est atomique.

Prochaines étapes : persistance serveur et authentification, gestion multidevise et taux datés, fournisseur de marché réel avec provenance, historique de prix et flux pour TWR et benchmarks, import enrichi et édition, puis fondamentaux et valorisation. Ajouter des tests métier avant chaque méthode financière.
