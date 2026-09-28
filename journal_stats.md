# 📒 Journal Crypto Pépite — statistiques

Signaux enregistrés : **27** — clôturés : **19** — en cours : **8**

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. Résultats en R bruts (1 R = distance entrée–SL), hors frais._

## Global

- Taux de réussite : **21 %** (4/19)
- Espérance : **-0.21 R** par trade
- Total : **-4.01 R** (≈ -4.01 USDT avec 1.0 USDT de risque)
- Durée moyenne : 2.4 h

### Par tranche de score

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| 60-79 | 13 | 3 | 23 % | -0.08 | -1.00 |
| 80-89 | 5 | 1 | 20 % | -0.40 | -2.01 |
| 90-100 | 1 | 0 | 0 % | -1.00 | -1.00 |

### Par setup

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 3 | 1 | 33 % | -0.00 | -0.01 |
| Cassure confirmée (clôture M15) + retest | 3 | 0 | 0 % | -1.00 | -3.00 |
| Rebond sur support H1 | 9 | 2 | 22 % | +0.00 | +0.04 |
| Rejet de résistance H1 | 4 | 1 | 25 % | -0.26 | -1.04 |

### Par contexte BTC

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| sens | 8 | 2 | 25 % | -0.26 | -2.05 |
| contre | 11 | 2 | 18 % | -0.18 | -1.96 |

### Par sens

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| LONG | 12 | 2 | 17 % | -0.25 | -2.96 |
| SHORT | 7 | 2 | 29 % | -0.15 | -1.05 |

### Par liquidité (volume 24h USDT)

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| n/d | 19 | 4 | 21 % | -0.21 | -4.01 |

## 🔍 Diagnostic entrée / SL / TP

_Basé sur 19 trades clôturés avec données complètes._

- Pertes en bougie ambiguë (TP et SL dans la même M15, comptées SL) : **0/15**
- Perdants passés par **+0.5 R** avant le SL : 9/15
- Perdants passés par **+1.0 R** avant le SL : 5/15
- Perdants passés par **+1.5 R** avant le SL : 4/15
- Perdants dont le TP a été touché **après** le SL (≤ 48 h) : **3/3** → élevé = SL trop serré
- Gagnants : recul moyen avant de gagner (MAE) **-0.60 R**, pire -0.76 R → proche de 0 = SL resserrable
- RR visé moyen : 3.33 | MFE moyen : +1.40 R | MFE médian : +0.92 R → MFE médian très inférieur au RR = TP trop loin

### Simulation : et si le TP était fixe ?

_Approximation : un trade gagne X R si son MFE a atteint X R avant le SL ; sinon résultat inchangé._

| TP | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|
| Actuel | 4/19 | 21 % | -0.21 | -4.01 |
| 1.0 R | 9/19 | 47 % | -0.05 | -1.00 |
| 1.5 R | 8/19 | 42 % | +0.05 | +1.00 |
| 2.0 R | 6/19 | 32 % | -0.05 | -1.00 |

⚠️ Seulement 19 trades clôturés : trop peu pour conclure (vise au moins 30 à 50).

## 👻 Signaux filtrés (contre BTC, NON tradés)

Enregistrés : **0** — clôturés : **0** — en cours : **0**

