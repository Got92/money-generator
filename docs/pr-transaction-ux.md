# Transactions et imports guidés

Un achat ou une vente expose six champs : opération, titre, portefeuille, date, quantité et prix. Les frais facultatifs et les paramètres de règlement sont accessibles dans une section avancée. Les opérations sur titres, cash et change disposent de champs adaptés.

## Audit et découpage proposé

1. Formulaire indépendant `src/transaction-ui.js`, recherche, édition et prévisualisation financière. Le formulaire monolithique de `app.js` affichait tous les types de champs simultanément. Le moteur gère déjà la chronologie, les règlements réels et les identifiants stables : ces règles sont conservées.
2. Import Trading 212 : éviter l'étape de mapping manuel déjà déductible du format et réutiliser les correspondances explicitement validées. L'adaptateur conservateur et la protection contre les doublons sont conservés.
3. Positions initiales : opération explicitement distincte d'un achat, PRU de référence, historique incomplet et absence de performance historique depuis l'origine.

Cette branche regroupe les trois lots pour permettre une recette complète des parcours et de leurs interactions.

## Comportement livré

La sélection d'une cotation précise préremplit sa devise ; les instruments locaux sont proposés même sans réseau. La recherche distante utilise l'API Yahoo Finance existante. Nom, symbole, place, devise et ISIN sont affichés lorsqu'ils sont connus. Une entreprise ou un ISIN communs ne fusionnent jamais deux cotations. Le mode avancé permet une saisie manuelle si le fournisseur est indisponible.

Un cours connu, daté et sourcé peut préremplir le prix d'une nouvelle opération, avec la mention « indicatif ». Le prix d'une transaction existante est conservé. Un PRU initial est toujours saisi par l'utilisateur. Les cours sélectionnés restent dans le brouillon jusqu'à confirmation ; leur profil est sauvegardé avec l'opération confirmée. Les historiques de change utilisent le cache existant du serveur : leur consultation peut alimenter le cache de marché, sans modifier les transactions.

`previewTransaction` dans `finance.js` utilise `positions`, `cashBalances`, `cashBalance` et `cashValue`. Il calcule le montant, les frais, les soldes avant/après, la quantité, le PRU en EUR et la pondération quand les cours et taux disponibles permettent le calcul. Aucun taux ni montant de règlement n'est inventé. Une observation postérieure à l'opération ne fournit pas de pondération historique. Les opérations du même jour conservent l'ordre enregistré ; la prévisualisation montre l'instant de l'opération et la validation couvre aussi les opérations ultérieures.

Le bouton « Vérifier l'opération » ouvre le récapitulatif. Seul « Confirmer l'enregistrement » sauvegarde. Annulation, retour, erreur de validation ou échec de sauvegarde ne conservent aucune modification de transaction. La confirmation est protégée contre les doubles soumissions. Aucun ordre n'est transmis à un courtier.

Trading 212 reconnu passe directement à la vérification des titres. Les correspondances sont réutilisées seulement pour le même portefeuille et symbole source, le même ISIN et la même devise, avec un identifiant local toujours cohérent et aucune correspondance contradictoire. Un ISIN seul ne suffit pas. Les choix réutilisés restent visibles et peuvent être revus. La première vérification ou toute ambiguïté reste explicite. Les formats inconnus conservent le mapping manuel. Les références courtier et les doublons probables restent bloquants ; une action ou un frais non interprété bloque le fichier entier avec une erreur.

Une `opening` crée une quantité et un coût de référence, sans débit de trésorerie. Elle doit précéder l'historique du titre et ne peut être ajoutée à une position déjà suivie, même clôturée. Les ventes ultérieures restent contrôlées. La performance historique et le XIRR sont rendus indisponibles pour les portefeuilles contenant une position initiale ; les PRU et plus-values sont explicitement présentés comme fondés sur une référence incomplète. Le calcul d'une performance limitée à la période de suivi reste un prolongement possible, non affiché ici.

## Stockage et compatibilité

Aucune table ni donnée existante n'est modifiée au chargement : les nouveaux champs `sourceTicker` et le type `opening` utilisent les payloads JSON déjà stockés. Aucune migration de structure n'est nécessaire. Le serveur et le moteur JavaScript valident le nouveau type. Les sauvegardes SQLite et les sauvegardes JSON existantes restent lisibles ; le test serveur couvre aussi l'export/restauration SQLite d'une position initiale. Un ancien exécutable ne comprend pas `opening` : garder la version mise à jour pour une base qui contient ce type.

Les modules de scoring et de valorisation ne sont pas modifiés.

## Validation

- `npm test` : tests financiers existants et cas de prévisualisation, règlement réel, change manquant, chronologie, même jour, positions initiales et réutilisation conservatrice des correspondances.
- `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` : stockage, API, sauvegardes et validation serveur, dont la restauration d'une position initiale.
- `npm run test:browser` : suite existante adaptée aux nouveaux parcours et scénario de transactions dédié.
- `npm run test:transactions-browser` : parcours complet hors ligne dans Chromium avec serveur et SQLite temporaires, données synthétiques et aucune base utilisateur. Achats, ventes excessives ou antidatées, édition invalidant une vente ultérieure, cash, dividendes, splits, corrections, change, position initiale, import reconnu et inconnu, réutilisation, doublons annulation, échec de sauvegarde et affichage mobile.

Résultats de la recette : 120 tests JavaScript, 108 tests Python et 17 scénarios navigateur réussis.
