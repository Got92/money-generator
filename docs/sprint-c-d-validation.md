# Recette des sprints C et D

## Parcours contrôlé

Le test navigateur `scripts/check-sprint-c-browser.mjs` crée un portefeuille sur une base temporaire, associe les colonnes d’un CSV fictif, transforme explicitement un symbole de courtier en symbole Atlas, vérifie que la prévisualisation n’écrit rien, confirme l’import, actualise les cours d’un fournisseur synthétique, vérifie la valorisation, recharge la page et revérifie le résultat. Les autres tests navigateur couvrent notamment la sauvegarde/restauration, le rapprochement, les scénarios, les cibles, les modules fondamentaux et les graphiques. Les tests ne touchent pas à une base personnelle.

## Vérification en direct le 16 novembre 2026

La commande facultative `ATLAS_DB=/chemin/jetable.sqlite3 .venv/bin/python scripts/check-real-companies.py` interroge Yahoo Finance pour SCHW, SPGI et AIR.PA. Les résultats dépendent du fournisseur et changent avec le temps. Le 16 novembre, les trois titres disposaient de quatre périodes annuelles et d’un instantané de valorisation. Les multiples disponibles comprenaient PER, PER prévisionnel et prix/chiffre d’affaires ; EV/EBITDA était également disponible pour SPGI et AIR.PA. Un seul instantané ne constitue pas un historique de multiples.

Le Company Quality Score était indisponible pour SCHW et SPGI, dont la classification sectorielle utilisable était inconnue ; pour AIR.PA la couverture pondérée atteignait 50,83 %, sous le seuil de 60 %. Ces cas indiquaient un motif explicite. Les scénarios DCF à hypothèses fictives (croissance 5 %, actualisation 10 %, croissance terminale 2 %) ont été calculés et contrôlés contre une formule indépendante pour SPGI et AIR.PA ; les entrées comparables nécessaires étaient indisponibles pour SCHW. Ce contrôle de cohérence ne valide pas les hypothèses financières ni ne constitue une recommandation.

## Limites de recette

Aucun relevé réel Trading 212 n’a été fourni. La correspondance de son format exact, la comparaison aux montants du courtier et un parcours de bout en bout sur des opérations réelles restent donc à vérifier. Le format de rapprochement fourni est normalisé pour Atlas. Les données Yahoo peuvent être incomplètes, périmées ou changer ; les indisponibilités restent visibles. Les opérations complexes comme les spin-offs et l’historique ajusté pour les splits ont les limites documentées dans le README.
