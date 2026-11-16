# Bilan P0 après PR 03 et PR 04

Le 16 novembre 2026, les PR GitHub 1 et 2 ont été vérifiées comme fusionnées. Leurs commits `695cf26` et `f7cb406` sont ancêtres de `origin/main` `b18d3e09d2d56f7c2c8c6ee65a09faf36eb8d4ad`.

L'utilisateur a demandé un sous-agent Terra 6.1 High par PR 03, 04 et 05. Les développements ont utilisé des worktrees isolés. La revue et l'intégration restent séquentielles : PR 03 sur cette base, PR 04 sur PR 03, puis PR 05 uniquement après la présente validation du socle P0. Les nouvelles PR ne sont pas fusionnées automatiquement.

## Résultats du contrôle combiné

| Vérification | Résultat |
|---|---|
| `npm test` | 73 tests réussis, aucun échec |
| `python -m unittest discover -s tests -p 'test_*.py'` dans `.venv` avec `ATLAS_DB` jetable | 30 tests réussis, aucun échec ; inclut 200 registres XIRR comparés à NumPy |
| `npm run test:browser` avec Chromium | Parcours historique/performance/benchmarks et parcours diversification réussis |
| `git diff --check` | Réussi |

Le worktree de contrôle distinct utilise uniquement des fichiers de test sous `TMPDIR` et une base `ATLAS_DB` dédiée. Aucune base personnelle n'est ouverte. La référence avant ces changements comptait 63 tests JS et 30 tests Python, avec le parcours navigateur également réussi.

## Fonctionnalités livrées

- Historiques SQLite persistants, migrations non destructives, reprises incrémentales et données conservées en panne : PR 01, déjà fusionnée.
- Dix périodes et TWR/XIRR avec cas de flux, frais, devises, zéro et lacunes : PR 02, déjà fusionnée.
- Six références de benchmarks, variantes Price Return et Total Return identifiées, proxy MSCI World explicite, comparaison EUR sur des extrémités communes sans déplacer le TWR autonome : PR 03. Un capital initial strictement positif est requis pour la comparaison ; la valeur finale peut être nulle.
- Secteur, industrie, devise de cotation, pays du profil et classe d'actifs, base investie ou avec cash signé, catégories inconnues et valorisations absentes explicites, sources/dates et dénominateur consultables : PR 04.

## Limites résiduelles

Le test réel de `^SP500TR` a récupéré 9 791 clôtures USD du 4 janvier 1988 au 13 novembre 2026. La série `^XNDX` est identifiée par Yahoo mais son téléchargement a échoué ; la disponibilité est signalée et aucun rendement n'est reconstitué. URTH reste un cours d'ETF proxy sans ses distributions. Les variantes TR non validées ne sont pas ajoutées artificiellement.

Les heures des flux, opérations sur titres, calendriers de bourse et expositions économiques par transparence des fonds restent hors périmètre. Les reports de cours/change et leurs limites sont signalés. Les classes d'actifs d'anciens profils restent inconnues jusqu'à actualisation. Les poids peuvent être négatifs ou dépasser 100 % avec un découvert ; une base non positive ou une valeur nécessaire manquante rend les pourcentages indisponibles. L'export JSON des portefeuilles ne remplace pas une sauvegarde SQLite des historiques.

Ce bilan autorise l'intégration technique de PR 05. Les ratios, scores, valorisations historiques et scénarios avancés restent dans les PR ultérieures du plan.
