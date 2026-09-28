# 📒 Journal Crypto Pépite — statistiques

Signaux enregistrés : **27** — clôturés : **22** — en cours : **5**

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. Résultats en R bruts (1 R = distance entrée–SL), hors frais._

## Global

- Taux de réussite : **27 %** (6/22)
- Espérance : **-0.03 R** par trade
- Total : **-0.59 R** (≈ -0.59 USDT avec 1.0 USDT de risque)
- Durée moyenne : 2.5 h

### Par tranche de score

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| 60-79 | 16 | 5 | 31 % | +0.15 | +2.42 |
| 80-89 | 5 | 1 | 20 % | -0.40 | -2.01 |
| 90-100 | 1 | 0 | 0 % | -1.00 | -1.00 |

### Par setup

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 3 | 1 | 33 % | -0.00 | -0.01 |
| Cassure confirmée (clôture M15) + retest | 3 | 0 | 0 % | -1.00 | -3.00 |
| Rebond sur support H1 | 9 | 2 | 22 % | +0.00 | +0.04 |
| Rejet de résistance H1 | 7 | 3 | 43 % | +0.34 | +2.38 |

### Par contexte BTC

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| sens | 11 | 4 | 36 % | +0.12 | +1.37 |
| contre | 11 | 2 | 18 % | -0.18 | -1.96 |

### Par sens

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| LONG | 12 | 2 | 17 % | -0.25 | -2.96 |
| SHORT | 10 | 4 | 40 % | +0.24 | +2.37 |

### Par liquidité (volume 24h USDT)

| | Trades | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|---|
| n/d | 22 | 6 | 27 % | -0.03 | -0.59 |

## 🔍 Diagnostic entrée / SL / TP

_Basé sur 22 trades clôturés avec données complètes._

- Pertes en bougie ambiguë (TP et SL dans la même M15, comptées SL) : **0/16**
- Perdants passés par **+0.5 R** avant le SL : 10/16
- Perdants passés par **+1.0 R** avant le SL : 6/16
- Perdants passés par **+1.5 R** avant le SL : 4/16
- Perdants dont le TP a été touché **après** le SL (≤ 48 h) : **3/3** → élevé = SL trop serré
- Gagnants : recul moyen avant de gagner (MAE) **-0.56 R**, pire -0.76 R → proche de 0 = SL resserrable
- RR visé moyen : 3.17 | MFE moyen : +1.48 R | MFE médian : +1.18 R → MFE médian très inférieur au RR = TP trop loin

### Simulation : et si le TP était fixe ?

_Approximation : un trade gagne X R si son MFE a atteint X R avant le SL ; sinon résultat inchangé._

| TP | Gagnants | Taux | R moyen | R total |
|---|---|---|---|---|
| Actuel | 6/22 | 27 % | -0.03 | -0.59 |
| 1.0 R | 12/22 | 55 % | +0.09 | +2.00 |
| 1.5 R | 10/22 | 45 % | +0.14 | +3.00 |
| 2.0 R | 8/22 | 36 % | +0.09 | +2.00 |

⚠️ Seulement 22 trades clôturés : trop peu pour conclure (vise au moins 30 à 50).

## 👻 Signaux filtrés (contre BTC, NON tradés)

Enregistrés : **0** — clôturés : **0** — en cours : **0**

