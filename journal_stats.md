# 📒 Journal Crypto Pépite V6.5 (statistiques de la logique V6.5)

_Mis à jour le 29/09/2026 23:19 UTC — 267 lignes dans le journal, 47 signaux ouverts, 179 trades clôturés en attente de simulation (48 h)._

Signaux réels V6.5 : **1** — clôturés : **0** — en cours : **1** — SHORT suivis en fantôme uniquement

_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés dans la même bougie M15 ; clôture au prix du moment après 48 h. 1 R = distance entrée–SL. R brut = hors frais ; R net = frais taker aller-retour déduits._


## Trades réels V6.5

Aucun trade V6.5 clôturé pour l'instant.

## Signaux fantômes V6.5 (non tradés : SHORT, WAIT, PREPARE)

Statuts : ATTENTE 7 | EN_COURS 3


## Gestion de sortie — tous les trades rejoués (réels toutes versions + fantômes)


### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 180 | RR visé moyen : 2.50 | MFE médian : **+0.87 R**
- Ont atteint +1 R : 46 % | +1,5 R : 38 % | +2 R : 28 %
- **MFE des perdants** (131 SL) : avaient atteint +0,5 R : 60 % | +1 R : 26 % | +1,5 R : 16 % avant de toucher le SL
- **MAE des gagnants** (48) : moyen -0.37 R | médian -0.29 R | pire -0.99 R | 40 % sont descendus au-delà de -0,5 R

### Sorties — ensemble — 1 trades rejoués bougie par bougie

| Gestion | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|
| A — TP / SL actuels | 0 % | -1.00 | -1.09 | -1.09 |
| B — SL à break-even dès +1 R | 0 % | -1.00 | -1.09 | -1.09 |
| C — SL à break-even dès +1,5 R | 0 % | -1.00 | -1.09 | -1.09 |
| D — rien avant +1,5 R, puis SL technique (extrême des 3 dernières M15) | 0 % | -1.00 | -1.09 | -1.09 |
| E — 50 % à +1 R, reste au TP (SL inchangé) | 0 % | -1.00 | -1.09 | -1.09 |
| F — TP fixe 1,5 R | 0 % | -1.00 | -1.09 | -1.09 |
| G — TP fixe 2 R | 0 % | -1.00 | -1.09 | -1.09 |

_Prudent : SL testé avant le TP dans chaque bougie ; BE / SL technique actifs à partir de la bougie suivante ; horizon 48 h. La ligne A peut différer légèrement du résultat réel (horizon fixe)._

## Famille V6 (toutes sous-versions 6.x cumulées, trades réels)

- Taux de réussite : **26 %** (5/19)
- Espérance : **-0.23 R brut** / **-0.31 R net** par trade
- Frais moyens : 0.08 R par trade
- Total : -4.45 R brut / **-5.97 R net** (≈ -5.97 USDT avec 1.0 USDT de risque)
- Durée moyenne : 2.1 h

### Par sous-version

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| 6.1 | 2 | 2 | 100 % | +1.52 | +1.45 | +2.90 |
| 6.2 | 1 | 0 | 0 % | -1.00 | -1.08 | -1.08 |
| 6.3 | 16 | 3 | 19 % | -0.41 | -0.49 | -7.79 |

### Par sens

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 19 | 5 | 26 % | -0.23 | -0.31 | -5.97 |

### MFE / MAE (jusqu'où les trades sont allés)

- Trades mesurés : 19 | RR visé moyen : 2.23 | MFE médian : **+0.87 R**
- Ont atteint +1 R : 37 % | +1,5 R : 26 % | +2 R : 16 %
- **MFE des perdants** (14 SL) : avaient atteint +0,5 R : 43 % | +1 R : 14 % | +1,5 R : 0 % avant de toucher le SL
- **MAE des gagnants** (5) : moyen -0.21 R | médian -0.17 R | pire -0.61 R | 20 % sont descendus au-delà de -0,5 R

⚠️ Seulement 19 trades clôturés : trop peu pour conclure (vise au moins 30 à 50 par catégorie).

---

## Versions précédentes (référence, non mélangé)


### Trades réels par version

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| 6.1 | 2 | 2 | 100 % | +1.52 | +1.45 | +2.90 |
| 6.2 | 1 | 0 | 0 % | -1.00 | -1.08 | -1.08 |
| 6.3 | 16 | 3 | 19 % | -0.41 | -0.49 | -7.79 |
| avant V6 | 54 | 13 | 24 % | -0.20 | -0.34 | -18.48 |

### Par setup (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| Cassure baissière (clôture M15) + retest | 12 | 1 | 8 % | -0.68 | -0.86 | -10.29 |
| Cassure confirmée (clôture M15) + retest | 5 | 0 | 0 % | -1.00 | -1.16 | -5.79 |
| Rebond sur support H1 | 36 | 13 | 36 % | +0.13 | +0.06 | +2.18 |
| Rejet de résistance H1 | 20 | 4 | 20 % | -0.32 | -0.53 | -10.55 |

### Par sens (toutes versions précédentes)

| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |
|---|---|---|---|---|---|---|
| LONG | 41 | 13 | 32 % | -0.01 | -0.09 | -3.61 |
| SHORT | 32 | 5 | 16 % | -0.46 | -0.65 | -20.84 |
