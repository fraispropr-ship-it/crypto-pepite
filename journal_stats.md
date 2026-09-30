# 📒 Journal Crypto Pépite V7.2 (statistiques de la logique V7.0)

_Mis à jour le 30/09/2026 10:19 UTC — 356 lignes dans le journal, 44 signaux ouverts, 235 trades clôturés en attente de simulation (48 h)._

Signaux réels V7.0 : **0** — clôturés : **0** — en cours : **0** — SHORT suivis en fantôme uniquement

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. 1 R = distance entrée–SL. R brut = hors frais ; R net = frais taker aller-retour déduits._


## Trades réels V7.0

Aucun trade V7.0 clôturé pour l'instant.

## Signaux fantômes V7.0 (non tradés : SHORT, WAIT, PREPARE)

Statuts : ATTENTE 3 | EN_COURS 1


## Gestion de sortie — tous les trades rejoués (réels toutes versions + fantômes)


### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 244 | RR visé moyen : 2.51 | MFE médian : **+0.84 R**
- Ont atteint +1 R : 45 % | +1,5 R : 38 % | +2 R : 26 %
- **MFE des perdants** (180 SL) : avaient atteint +0,5 R : 61 % | +1 R : 27 % | +1,5 R : 17 % avant de toucher le SL
- **MAE des gagnants** (63) : moyen -0.39 R | médian -0.33 R | pire -0.99 R | 41 % sont descendus au-delà de -0,5 R

### Sorties — ensemble — 9 trades rejoués bougie par bougie

| Gestion | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|
| A — TP / SL actuels | 22 % | -0.18 | -0.30 | -2.73 |
| B — SL à break-even dès +1 R | 0 % | -0.56 | -0.68 | -6.09 |
| C — SL à break-even dès +1,5 R | 22 % | +0.04 | -0.08 | -0.73 |
| D — rien avant +1,5 R, puis SL technique (extrême des 3 dernières M15) | 44 % | -0.09 | -0.22 | -1.94 |
| E — 50 % à +1 R, reste au TP (SL inchangé) | 22 % | -0.15 | -0.27 | -2.42 |
| F — TP fixe 1,5 R | 44 % | +0.11 | -0.01 | -0.09 |
| G — TP fixe 2 R | 33 % | +0.00 | -0.12 | -1.09 |

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
| avant V6 | 55 | 13 | 24 % | -0.21 | -0.35 | -19.49 |

### Par setup (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 13 | 1 | 8 % | -0.71 | -0.87 | -11.30 |
| Cassure confirmée (clôture M15) + retest | 5 | 0 | 0 % | -1.00 | -1.16 | -5.79 |
| Rebond sur support H1 | 50 | 16 | 32 % | -0.01 | -0.10 | -4.77 |
| Rejet de résistance H1 | 20 | 4 | 20 % | -0.32 | -0.53 | -10.55 |

### Par sens (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 55 | 16 | 29 % | -0.10 | -0.19 | -10.56 |
| SHORT | 33 | 5 | 15 % | -0.48 | -0.66 | -21.85 |
