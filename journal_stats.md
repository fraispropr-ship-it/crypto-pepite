# 📒 Journal Crypto Pépite V7.5 (statistiques de la logique V7.5)

_Mis à jour le 07/10/2026 09:49 UTC — 2094 lignes dans le journal, 66 signaux ouverts, 392 trades clôturés en attente de simulation (48 h)._

Signaux réels V7.5 : **2** — clôturés : **0** — en cours : **2** — SHORT suivis en fantôme uniquement

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. 1 R = distance entrée–SL. R brut = hors frais ; R net = frais taker aller-retour déduits._


## Trades réels V7.5

Aucun trade V7.5 clôturé pour l'instant.

## Signaux fantômes V7.5 (non tradés : SHORT, WAIT, PREPARE)

Statuts : ATTENTE 9 | EN_COURS 6


## Gestion de sortie — tous les trades rejoués (réels toutes versions + fantômes)


### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 1480 | RR visé moyen : 2.46 | MFE médian : **+0.98 R**
- Ont atteint +1 R : 50 % | +1,5 R : 39 % | +2 R : 27 %
- **MFE des perdants** (1031 SL) : avaient atteint +0,5 R : 56 % | +1 R : 28 % | +1,5 R : 13 % avant de toucher le SL
- **MAE des gagnants** (441) : moyen -0.38 R | médian -0.36 R | pire -1.00 R | 36 % sont descendus au-delà de -0,5 R

### Sorties — ensemble — 1088 trades rejoués bougie par bougie

| Gestion | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|
| A — TP / SL actuels | 31 % | -0.03 | -0.22 | -235.66 |
| B — SL à break-even dès +1 R | 23 % | -0.00 | -0.19 | -204.97 |
| C — SL à break-even dès +1,5 R | 28 % | +0.00 | -0.18 | -196.86 |
| D — rien avant +1,5 R, puis SL technique (extrême des 3 dernières M15) | 39 % | +0.03 | -0.16 | -170.65 |
| E — 50 % à +1 R, reste au TP (SL inchangé) | 31 % | -0.01 | -0.19 | -211.98 |
| F — TP fixe 1,5 R | 41 % | +0.02 | -0.17 | -183.45 |
| G — TP fixe 2 R | 33 % | -0.01 | -0.20 | -215.91 |

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
| 7.0 | 25 | 6 | 24 % | -0.25 | -0.39 | -9.71 |
| 7.4 | 58 | 21 | 36 % | +0.06 | -0.11 | -6.11 |
| avant V6 | 56 | 13 | 23 % | -0.22 | -0.37 | -20.54 |

### Par setup (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 14 | 1 | 7 % | -0.73 | -0.88 | -12.35 |
| Cassure confirmée (clôture M15) + retest | 5 | 0 | 0 % | -1.00 | -1.16 | -5.79 |
| Rebond sur support H1 | 133 | 43 | 32 % | -0.02 | -0.15 | -20.59 |
| Rejet de résistance H1 | 20 | 4 | 20 % | -0.32 | -0.53 | -10.55 |

### Par sens (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 138 | 43 | 31 % | -0.06 | -0.19 | -26.38 |
| SHORT | 34 | 5 | 15 % | -0.49 | -0.67 | -22.90 |
