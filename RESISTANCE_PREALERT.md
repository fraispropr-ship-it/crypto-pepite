# Préalerte résistance M15

Module expérimental séparé de Radar ALT H1, sans ordre automatique.

- Univers Zoomex crypto USDT, volume quotidien >= 10 M USDT, 100 paires maximum, exclusions de Radar ALT.
- Scan GitHub toutes les 15 minutes (07/22/37/52 UTC ; horaire réel dépend de la file GitHub).
- 200 bougies M15, clôturées uniquement ; pivots confirmés par deux bougies à droite ; quatre dernières bougies exclues de la construction du niveau.
- Trois tests distincts minimum, séparés par 4 bougies et un repli de 0,7 ATR ; au moins 16 bougies entre premier et dernier test.
- Zone +/- 0,25 ATR ; proximité <= 0,8 ATR sous la zone ; compression ou creux remontants ; aucune clôture déjà au-dessus et vérification du prix courant.
- Anti-doublon : zone proche muette 48 h. Les alertes Telegram sont des observations expérimentales, pas des signaux d'achat.
- OI : quantité de base Zoomex, comparée au dernier scan seulement si espacement 5 à 45 min ; première observation indisponible. Ne mesure pas de nouveaux longs seuls.
- Flux : delta des transactions taker Zoomex observées dans les dernières 15 min, maximum 1 000 transactions ; nombre et durée réels affichés. Jamais présenté comme CVD M15 exhaustif. Minimum 20 transactions, durée >= 30 s, dernière transaction <= 60 s.
- Le couple OI >= +0,5 % et achats taker >= 55 % enrichit la lecture, sans constituer un filtre obligatoire. Une préalerte structurelle peut partir sans confirmation OI/flux ; cette absence est explicite.
- resistance_state.json conserve zones et dernières observations OI. resistance_events.jsonl journalise préalertes, clôtures au-dessus, invalidations et réintégrations détectées. Aucun résultat de rentabilité n'est établi.
- Les mises à jour du code lancent les tests et un diagnostic sans notification. Exécution manuelle : dry_run=true par défaut.

Tests : python -m unittest -v test_radar_resistance.py

Limites : pas de collecte WebSocket continue, ni CVD historique complet, ni backtest de rentabilité. Le suivi des événements est effectué uniquement pour les paires encore présentes dans l'univers liquide. L'anti-doublon dépend de l'enregistrement GitHub de l'état ; une panne de sauvegarde après envoi peut permettre un doublon au prochain scan.
