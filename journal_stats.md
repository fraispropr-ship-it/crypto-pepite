# 📒 Journal Crypto Pépite V7.4 (statistiques de la logique V7.4)

_Mis à jour le 30/09/2026 16:19 UTC — 470 lignes dans le journal, 39 signaux ouverts, 306 trades clôturés en attente de simulation (48 h)._

Signaux réels V7.4 : **6** — clôturés : **0** — en cours : **6** — SHORT suivis en fantôme uniquement

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. 1 R = distance entrée–SL. R brut = hors frais ; R net = frais taker aller-retour déduits._


## Trades réels V7.4

Aucun trade V7.4 clôturé pour l'instant.

## Signaux fantômes V7.4 (non tradés : SHORT, WAIT, PREPARE)

Statuts : ATTENTE 3 | EN_COURS 1


## Gestion de sortie — tous les trades rejoués (réels toutes versions + fantômes)


### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 327 | RR visé moyen : 2.49 | MFE médian : **+0.87 R**
- Ont atteint +1 R : 47 % | +1,5 R : 39 % | +2 R : 28 %
- **MFE des perdants** (238 SL) : avaient atteint +0,5 R : 57 % | +1 R : 27 % | +1,5 R : 17 % avant de toucher le SL
- **MAE des gagnants** (88) : moyen -0.40 R | médian -0.37 R | pire -0.99 R | 41 % sont descendus au-delà de -0,5 R

### Sorties — ensemble — 21 trades rejoués bougie par bougie

| Gestion | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|
| A — TP / SL actuels | 19 % | -0.25 | -0.35 | -7.31 |
| B — SL à break-even dès +1 R | 10 % | -0.21 | -0.31 | -6.47 |
| C — SL à break-even dès +1,5 R | 19 % | -0.06 | -0.16 | -3.31 |
| D — rien avant +1,5 R, puis SL technique (extrême des 3 dernières M15) | 38 % | -0.05 | -0.15 | -3.23 |
| E — 50 % à +1 R, reste au TP (SL inchangé) | 24 % | -0.10 | -0.20 | -4.22 |
| F — TP fixe 1,5 R | 38 % | -0.01 | -0.11 | -2.30 |
| G — TP fixe 2 R | 29 % | -0.10 | -0.20 | -4.30 |

_Prudent : SL testé avant le TP dans chaque bougie ; BE / SL technique actifs à partir de la bougie suivante ; horizon 48 h. La ligne A peut différer légèrement du résultat réel (horizon fixe)._

## Famille V6 (toutes sous-versions 6.x cumulées, trades réels)

- Taux de réussite : **24 %** (8/33)
- Espérance : **-0.29 R brut** / **-0.39 R net** par trade
- Frais moyens : 0.10 R par trade
- Total : -9.63 R brut / **-12.92 R net** (≈ -12.92 USDT avec 1.0 USDT de risque)
- Durée moyenne : 2.5 h

### Par sous-version

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| 6.1 | 2 | 2 | 100 % | +1.52 | +1.45 | +2.90 |
| 6.2 | 1 | 0 | 0 % | -1.00 | -1.08 | -1.08 |
| 6.3 | 21 | 3 | 14 % | -0.55 | -0.63 | -13.24 |
| 6.5 | 9 | 3 | 33 % | -0.02 | -0.17 | -1.50 |

### Par sens

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 33 | 8 | 24 % | -0.29 | -0.39 | -12.92 |

### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 33 | RR visé moyen : 2.40 | MFE médian : **+0.74 R**
- Ont atteint +1 R : 36 % | +1,5 R : 27 % | +2 R : 18 %
- **MFE des perdants** (25 SL) : avaient atteint +0,5 R : 48 % | +1 R : 16 % | +1,5 R : 4 % avant de toucher le SL
- **MAE des gagnants** (8) : moyen -0.25 R | médian -0.16 R | pire -0.80 R | 25 % sont descendus au-delà de -0,5 R


---

## Versions précédentes (référence, non mélangé)


### Trades réels par version

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| 6.1 | 2 | 2 | 100 % | +1.52 | +1.45 | +2.90 |
| 6.2 | 1 | 0 | 0 % | -1.00 | -1.08 | -1.08 |
| 6.3 | 21 | 3 | 14 % | -0.55 | -0.63 | -13.24 |
| 6.5 | 9 | 3 | 33 % | -0.02 | -0.17 | -1.50 |
| 7.0 | 18 | 4 | 22 % | -0.32 | -0.48 | -8.55 |
| avant V6 | 56 | 13 | 23 % | -0.22 | -0.37 | -20.54 |

### Par setup (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 14 | 1 | 7 % | -0.73 | -0.88 | -12.35 |
| Cassure confirmée (clôture M15) + retest | 5 | 0 | 0 % | -1.00 | -1.16 | -5.79 |
| Rebond sur support H1 | 68 | 20 | 29 % | -0.09 | -0.20 | -13.32 |
| Rejet de résistance H1 | 20 | 4 | 20 % | -0.32 | -0.53 | -10.55 |

### Par sens (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 73 | 20 | 27 % | -0.15 | -0.26 | -19.11 |
| SHORT | 34 | 5 | 15 % | -0.49 | -0.67 | -22.90 |
