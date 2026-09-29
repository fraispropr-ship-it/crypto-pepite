# 📒 Journal Crypto Pépite V6.0 — statistiques

Signaux réels V6.0 : **0** — clôturés : **0** — en cours : **0**

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. 1 R = distance entrée–SL. R brut = hors frais ; R net = frais taker aller-retour déduits._


## Trades réels V6.0

Aucun trade V6.0 clôturé pour l'instant.

## Signaux fantômes V6.0 (non tradés, suivis pour tester les filtres)

Statuts : ATTENTE 17 | EN_COURS 3


## Sorties — tous les trades réels (V6 + historique)


### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 17
- RR visé moyen : 3.11 | MFE médian : **+0.87 R**
- Ont atteint +1 R : 41 % | +1,5 R : 35 % | +2 R : 29 %
- MAE moyen des gagnants : -0.64 R

### Simulation de sorties (17 trades avec MFE)

| Scénario | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|
| Actuel (TP sur zone) | 18 % | -0.39 | -0.52 | -8.83 |
| TP plafonné à 1,5 R | 35 % | -0.12 | -0.24 | -4.15 |
| TP plafonné à 2 R | 29 % | -0.12 | -0.25 | -4.20 |
| 50 % à 1 R + reste au TP | 18 % | -0.28 | -0.41 | -6.99 |
| 50 % à 1 R + reste plafonné à 2 R | 29 % | -0.15 | -0.28 | -4.68 |

_Approximation : basée sur le plus haut favorable atteint avant la sortie ; la bougie du SL n'est pas comptée dans le MFE (prudent)._

---


## Historique avant V6 (référence, non mélangé)

- Taux de réussite : **24 %** (11/46)
- Espérance : **-0.17 R brut** / **-0.31 R net** par trade
- Frais moyens : 0.15 R par trade
- Total : -7.79 R brut / **-14.47 R net** (≈ -14.47 USDT avec 1.0 USDT de risque)
- Durée moyenne : 2.8 h

### Par tranche de score

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| <80 | 27 | 8 | 30 % | +0.08 | -0.08 | -2.28 |
| 80-89 | 17 | 3 | 18 % | -0.47 | -0.59 | -9.99 |
| 90-100 | 2 | 0 | 0 % | -1.00 | -1.10 | -2.20 |

### Par setup

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 8 | 1 | 12 % | -0.63 | -0.83 | -6.68 |
| Cassure confirmée (clôture M15) + retest | 5 | 0 | 0 % | -1.00 | -1.16 | -5.79 |
| Rebond sur support H1 | 15 | 6 | 40 % | +0.45 | +0.38 | +5.74 |
| Rejet de résistance H1 | 18 | 4 | 22 % | -0.25 | -0.43 | -7.74 |

### Par contexte BTC détaillé (H4-H1)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| n/d (avant V6) | 46 | 11 | 24 % | -0.17 | -0.31 | -14.47 |

### Par sens

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 20 | 6 | 30 % | +0.08 | -0.00 | -0.05 |
| SHORT | 26 | 5 | 19 % | -0.36 | -0.55 | -14.42 |
