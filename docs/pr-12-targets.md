# Allocations cibles

Dans Portefeuilles, les cibles sont associées au portefeuille sélectionné. Ajouter des lignes pour les positions (ticker exact), secteurs ou industries (libellé exact fourni par la cotation). Les bornes minimale et maximale déterminent les alertes. Chaque dimension peut être partielle, mais ses cibles ne doivent pas dépasser 100 %. Les poids sont saisis en pourcentage et conservés en fractions entre 0 et 1.

Le dénominateur est choisi explicitement : positions investies seules ou positions plus liquidités signées. Les cours et changes indisponibles empêchent le calcul ; une classification inconnue empêche d'affirmer un poids sectoriel ou industriel exact. Les liquidités ne sont pas attribuées à une position ou une classification.

`GET /api/portfolio/targets?portfolioId=...` renvoie `{portfolioId,basis,targets,revision}` ; `PUT` accepte le même objet, avec révision facultative pour les clients sans contrôle de concurrence. `basis` vaut `invested` ou `total`, et chaque cible comprend `dimension`, `key`, `target`, `min`, `max`. Une révision périmée retourne 409. La migration 6 conserve ces configurations indépendamment des tables de portefeuilles réécrites lors des sauvegardes ; aucune transaction n'est créée.
