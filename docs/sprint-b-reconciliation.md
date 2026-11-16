# Rapprochement d’un portefeuille

Le format ci-dessous est **normalisé pour Atlas**. Le rapprochement ne lit pas directement un relevé Trading 212 : les colonnes et montants doivent être associés et vérifiés à partir de votre relevé. Un import distinct des transactions reconnaît un sous-ensemble des exports Trading 212, conserve le règlement net effectivement déclaré même dans une devise différente et refuse les lignes ambiguës. Le registre conserve un identifiant interne par symbole fournisseur, avec ISIN, place et devise lorsqu’ils sont connus. La recherche d’instruments dans Research affiche le symbole et la place ; utilisez le symbole Atlas de la transaction dans `ticker`. Vérifiez aussi la devise, la place et l’ISIN du relevé : un même émetteur peut avoir plusieurs cotations. Si l’ISIN et la place sont absents du relevé, ou si un identifiant fourni est absent de la fiche Yahoo, le contrôle d’identité est indiqué « non vérifiable » ; aucune correspondance automatique n’est supposée.

Dans Portefeuilles → Rapprochement, sélectionnez un CSV UTF-8 ou un JSON normalisé puis définissez les tolérances (par défaut 0,000001 titre et 0,02 unité monétaire). Le rapprochement est un rapport temporaire ; il ne modifie pas les transactions. `from` et `asOf` délimitent inclusivement la période des frais et dividendes. Les positions et soldes sont comparés à la clôture de `asOf`, sur toutes les opérations antérieures. Le CSV accepte une virgule ou un point-virgule comme séparateur ; les décimales utilisent un point.

```csv
type,from,asOf,positionsComplete,cashComplete,ticker,quantity,averageEUR,valueEUR,realizedEUR,currency,amount,isin,exchange
meta,2024-01-01,2024-01-19,true,true,,,,,,,,,
position,,,,,AAA,30,55.1,1800,98,,,,
position,,,,,BBB,0,,,34.2,,,,
position,,,,,CCC,2,86.66666667,180,23.33333333,,,,
cash,,,,,,,,,,EUR,8325,,
cash,,,,,,,,,,USD,1048,,
fee,,,,,,,,,,EUR,5,,
fee,,,,,,,,,,USD,2,,
dividend,,,,,,,,,,EUR,30,,
dividend,,,,,,,,,,USD,10,,
```

Une seule ligne `meta` est requise. `positionsComplete` signifie que le relevé comprend **toutes** les positions à cette date ; une position absente est alors considérée comme nulle, ce qui permet de vérifier les clôtures. `cashComplete` signifie que tous les soldes en devise sont présents ; un solde absent est alors considéré comme nul. Sinon, utilisez `false` et les omissions resteront non vérifiables. Pour confirmer qu’aucun frais ou dividende n’existe sur la période, utilisez une ligne `fees_none` ou `dividends_none` respectivement ; une rubrique absente n’est pas considérée comme nulle. Si des frais ou dividendes existent, renseignez un total par devise. Les frais de transaction sont ceux des achats et ventes ; les frais externes, retenues fiscales, dividendes bruts et nets doivent être comparés selon le traitement du courtier et peuvent nécessiter une explication manuelle.

La ligne `meta` peut inclure une colonne facultative `totalEUR` pour comparer la valeur totale du portefeuille en EUR ; le contrôle reste indisponible si un cours ou un taux nécessaire est absent ou trop ancien. `quantity` est un nombre de titres. `averageEUR`, `valueEUR` et `realizedEUR` sont facultatifs et exprimés en EUR, avec les frais dans le PRU et le gain ; la valeur doit être une valeur de position, pas le prix unitaire. `amount` est exprimé dans la devise précisée. Les écarts numériques sont calculés Atlas moins courtier. Les contrôles manquants, cours ou taux trop anciens et correspondances d’identité non confirmées sont signalés « non vérifiable », jamais « conforme ». Une position clôturée peut être incluse avec quantité zéro et `realizedEUR` pour contrôler le gain réalisé. En mode de trésorerie convertie, les soldes étrangers du courtier ne sont pas reconstruits : utilisez le mode multidevise pour les rapprocher.

Le calcul utilise le dernier cours enregistré à la date du relevé ou dans les sept jours précédents et le taux FX antérieur de sept jours maximum pour les conversions du rapport. Une fiche actuelle ne permet pas de reconstituer automatiquement un cours ancien : le contrôle de valeur sera alors indisponible. Vérifiez l’heure de valorisation, les jours de marché, les cotations différées, le change, les frais, la fiscalité et la méthode du PRU avant d’expliquer un écart. Le report indique des causes possibles, pas une attribution prouvée.

## Référence de test

`tests/fixtures/reference-portfolio.json` est un portefeuille **fictif** (identifiants compris), avec 20 opérations, et ne constitue pas un relevé Trading 212. Les résultats attendus sont calculés séparément : AAA coûte 2 204 € pour 20 titres, puis la vente de 5 dégage 649 − 551 = 98 € ; le split double les 15 titres restants sans changer le coût de 1 653 €, soit 55,10 € par titre. BBB coûte (200 + 1) × 0,9 = 180,90 € et sa vente rapporte (240 − 1) × 0,9 = 215,10 €, soit 34,20 € réalisé. CCC conserve 2 titres au coût de 173,333… €, avec 23,333… € réalisé. Les soldes sont 8 325 € et 1 048 USD ; frais 5 € et 2 USD ; dividendes 30 € et 10 USD. Les valeurs attendues sont 1 800 € pour AAA et 180 € pour CCC. Les tests utilisent les tolérances indiquées ci-dessus et exigent zéro écart et zéro contrôle non vérifiable sur ces données.

Pour une recette réelle, il faut un export de courtier anonymisé et des résultats attendus établis indépendamment, avec les dates et conventions de valorisation du courtier ; le test synthétique ne remplace pas cette recette.
