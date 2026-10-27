# Audit initial — recherche intraday indépendante

Statut : **audit partiel ; aucun nouveau backtest ni avantage démontré**. Aucune modification de main, Radar Alt ou Telegram.

## Sources examinées

- Branche research/trend-retest-signal-quality : trend_retest_1y.py, trend_retest_signal_quality.py, radar_v4_trend_retest.py, radar_v3_benchmark.py.
- Logs Actions : runs 40484120743 et 40490511237.
- Ces résultats doivent être interprétés comme les sorties des anciens programmes, non comme une nouvelle validation.

## Résultats précédents

- Trend Retest un an : 248 trades, -78,758 R, -0,3176 R/trade, PF 0,602. Dernière période annoncée : 45 trades, -0,041 R/trade, PF 0,940.
- Modèle de scoring : fenêtre avril 2026, 7 trades sélectionnés, -1,1023 R/trade, PF 0 ; fenêtre juillet 2026, 10 trades, -0,4999 R/trade, PF 0,434. Ce sont de très petits échantillons.
- L'étude signale que la période de validation avait déjà été explorée, que l'univers est fixe et sélectionné a posteriori, et qu'elle ne simule pas un portefeuille global ni le funding.

## Points techniques identifiés

- Les bougies proviennent de l'API publique Zoomex ; accès ponctuel BTC H1 vérifié, sans démontrer la couverture pluriannuelle des 20 actifs.
- Le téléchargement M15 vérifie la continuité interne après déduplication, mais ne vérifie pas explicitement que les bornes de début et de fin sont couvertes. Un historique tronqué peut donc passer ce contrôle s'il n'y a pas de trou interne ; tester les dates et le listing effectifs.
- La simulation utilise 0,06 % par côté et 0,02 % de slippage par côté comme hypothèses, pas comme frais personnels ou exécutions réellement vérifiés.
- Le moteur favorise le stop si stop et cible apparaissent dans une même bougie M15. C'est prudent, mais ne reconstitue pas le chemin intrabar réel.
- Le scoring collecte explicitement les signaux pouvant se chevaucher. Le nombre de résultats ne représente donc pas nécessairement des positions négociables avec deux entrées maximum par jour.
- Le risque est normalisé à la distance entrée-stop brute ; frais, slippage à la sortie et gaps peuvent entraîner une perte supérieure à 1 R. Il faut distinguer risque prévu et perte réalisée.
- Le funding, le spread réel, les contraintes de taille minimale, les arrondis et le capital/marge globale ne sont pas simulés.
- La sélection des 20 actifs actuels induit un biais de survivance et de liquidité ; elle ne démontre pas leur éligibilité historique.

## Conditions avant toute conclusion

Construire un jeu horodaté et versionné avec contrôles OHLC, doublons, trous, listings, volume, couverture du funding et coûts ; figer l'univers et les règles de sélection ex ante ; définir et conserver une vraie période finale inédite ; séparer chronologiquement apprentissage et validation avec purge des trades chevauchants ; comparer quatre familles distinctes ; tester coûts normaux et dégradés ; simuler les priorités de signaux simultanés, la marge, le risque, les deux entrées par jour et 12 h maximum ; rapporter toutes les variantes et intervalles d'incertitude. Une période déjà examinée doit être traitée comme développement, même si elle avait été appelée holdout.

Aucune stratégie candidate n'est désignée à ce stade. Les résultats demandés, le code de recherche et les simulations restent à réaliser.
