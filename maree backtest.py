# ==============================================================================
#  MARÉE — BACKTEST v1.0 (fichier autonome, ne dépend d'aucun autre scanner)
#
#  Principe, à l'opposé des 4 scanners précédents :
#    - On ne cherche plus un point d'entrée précis en M15. On suit la TENDANCE DE FOND,
#      en bougies JOURNALIÈRES, sur toutes les paires liquides, à la hausse comme à la baisse.
#    - Beaucoup de petites pertes, quelques très gros gains : pas de TP, on laisse courir
#      et c'est un stop suiveur qui fait sortir.
#    - Stop très large (plusieurs fois le mouvement moyen d'une journée) : les frais ne
#      pèsent presque plus rien, et le bruit intraday ne sort plus le trade.
#    - Un seul passage par jour, quelques trades par semaine.
#
#  Règles (fixées AVANT de voir le moindre résultat, valeurs classiques du suivi de tendance) :
#    1. Paire liquide : volume moyen des 30 derniers jours >= LIQ_MIN USDT par jour.
#    2. Signal LONG  : la clôture du jour dépasse la plus haute clôture des N jours précédents.
#       Signal SHORT : la clôture du jour passe sous la plus basse clôture des N jours précédents.
#    3. Entrée le lendemain à l'ouverture (pénalisée de SLIP_ENTREE : tu ne lis pas l'alerte
#       à minuit pile).
#    4. Stop initial à K x ATR(20 jours) de l'entrée. 1 R = cette distance. Risque 1 USDT.
#    5. Stop suiveur : chaque soir, le stop remonte à (plus haute clôture depuis l'entrée
#       - K x ATR). Il ne redescend jamais. Miroir pour les SHORT.
#    6. Pas de TP. MAX_POS positions ouvertes au maximum (les plus liquides d'abord).
#
#  Coûts comptés : frais taker 0,06 % par côté, glissement à l'entrée et au stop,
#  funding supposé payé par les LONG (0,03 % par jour), jamais reçu par les SHORT.
#
#  Honnêteté du test :
#    - Réglage principal déclaré d'avance : N = 50, K = 3. Les réglages N = 20 et N = 100
#      sont affichés à côté uniquement pour voir si le résultat est robuste (pas pour choisir
#      le meilleur après coup).
#    - L'historique est coupé en deux moitiés : le réglage principal doit être positif
#      sur CHACUNE des deux.
#    - Limite connue : les paires sont celles cotées aujourd'hui (les paires disparues
#      manquent à l'historique).
#
#  Utilisation (Colab) :
#     !python maree_backtest.py
#  Options : --paires 100 --jours 1500 --max-pos 10 --retelecharger
#  Résultats : maree_stats.md (rapport) et maree_trades.csv (un trade par ligne).
# ==============================================================================
import argparse, os, pickle, sys, time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

VERSION = "1.0"

# ---------------- RÈGLES (ne pas les ajuster après avoir vu les résultats) ----------------
N_PRINCIPAL  = 50              # réglage principal : plus haut / plus bas de 50 jours
N_ROBUSTESSE = (20, 50, 100)   # affichés pour vérifier que le résultat ne tient pas à un seul chiffre
K_ATR        = 3.0             # distance du stop, en ATR 20 jours
ATR_N        = 20
LIQ_MIN      = 10_000_000      # volume moyen 30 jours minimum (USDT par jour)
MAX_POS      = 10              # positions ouvertes au maximum
RISQUE       = 1.0             # USDT par trade (1 R)

# ---------------- COÛTS ----------------
FRAIS_TAKER  = 0.0006          # par côté
SLIP_ENTREE  = 0.005           # 0,5 % contre toi à l'entrée (alerte lue quelques heures après)
SLIP_STOP    = 0.002           # 0,2 % contre toi à la sortie au stop
FUNDING_JOUR = 0.0003          # payé par les LONG chaque jour ; les SHORT ne reçoivent rien

JOUR = 86_400_000
SOURCES = {"Zoomex": "https://openapi.zoomex.com/cloud/trade/v3/market/",
           "Bybit":  "https://api.bybit.com/v5/market/"}
SRC = None
SESS = requests.Session()


# ---------------- TÉLÉCHARGEMENT ----------------
def api(path, **params):
    for essai in range(4):
        try:
            r = SESS.get(SOURCES[SRC] + path, params=params, timeout=20)
            if r.status_code in (403, 451):
                return "BLOQUE"
            j = r.json()
            if j.get("retCode") == 0:
                return j["result"]
        except Exception:
            pass
        time.sleep(1 + essai)
    return None


def choisir_source():
    global SRC
    for nom in SOURCES:
        SRC = nom
        res = api("tickers", category="linear", symbol="BTCUSDT")
        if isinstance(res, dict) and res.get("list"):
            print(f"Données de marché : {nom}")
            return
        print(f"  {nom} inaccessible depuis cette connexion")
    sys.exit("⛔ Aucune source accessible depuis cette connexion.")


def liste_paires(n):
    res = api("tickers", category="linear")
    df = pd.DataFrame(res["list"])
    df["turnover24h"] = pd.to_numeric(df["turnover24h"], errors="coerce")
    df = df[df.symbol.str.endswith("USDT")]
    return list(df.sort_values("turnover24h", ascending=False).symbol.head(n))


def telecharger(sym, debut, fin):
    lignes, cur = [], fin
    while cur > debut:
        res = api("kline", category="linear", symbol=sym, interval="D",
                  start=int(debut), end=int(cur), limit=1000)
        if not isinstance(res, dict) or not res.get("list"):
            break
        lst = res["list"]
        lignes += lst
        plus_vieux = min(int(x[0]) for x in lst)
        if len(lst) < 1000 or plus_vieux <= debut:
            break
        cur = plus_vieux - 1
        time.sleep(0.12)
    if not lignes:
        return None
    df = pd.DataFrame(lignes)
    df = df.iloc[:, :7] if df.shape[1] >= 7 else df.iloc[:, :6].assign(x=np.nan)
    df.columns = ["t", "o", "h", "l", "c", "v", "to"]
    df = df.astype(float).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    if df["to"].isna().all():
        df["to"] = df.v * df.c
    return df[df.t + JOUR <= fin].reset_index(drop=True)      # bougies clôturées uniquement


def charger_donnees(jours, npaires, forcer):
    fichier = f"maree_data_{jours}j_{npaires}p.pkl"
    if os.path.exists(fichier) and not forcer:
        with open(fichier, "rb") as f:
            sauve = pickle.load(f)
        print(f"Données reprises de {fichier} (ajoute --retelecharger pour les rafraîchir)")
        return sauve
    choisir_source()
    fin = int(time.time() * 1000)
    debut = fin - jours * JOUR
    syms = liste_paires(npaires)
    data = {}
    for i, sym in enumerate(syms, 1):
        df = telecharger(sym, debut, fin)
        if df is not None and len(df) >= 120:
            data[sym] = df
        if i % 10 == 0 or i == len(syms):
            print(f"  téléchargement {i}/{len(syms)}", flush=True)
    sauve = dict(data=data, source=SRC)
    with open(fichier, "wb") as f:
        pickle.dump(sauve, f)
    return sauve


# ---------------- PRÉPARATION ----------------
def tableaux(data):
    """Aligne toutes les paires sur le même calendrier (une ligne par jour, une colonne par paire)."""
    def tab(col):
        return pd.DataFrame({s: d.set_index("t")[col] for s, d in data.items()}).sort_index()
    O, H, L, C, TO = tab("o"), tab("h"), tab("l"), tab("c"), tab("to")
    prec = C.shift(1)
    tr = pd.concat([H - L, (H - prec).abs(), (L - prec).abs()]).groupby(level=0).max()
    atr = tr.ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean()
    liq = TO.rolling(30, min_periods=30).mean()
    return dict(O=O, H=H, L=L, C=C, ATR=atr, LIQ=liq, jours=O.index.values, syms=list(O.columns))


# ---------------- MOTEUR ----------------
def backtest(T, n, k=K_ATR, max_pos=MAX_POS):
    """Rejoue la stratégie jour par jour. Aucune information du futur n'est utilisée :
    le signal est calculé à la clôture du jour i, l'entrée se fait à l'ouverture du jour i+1."""
    O, H, L, C = (T[x].values for x in "OHLC")
    A, LIQ = T["ATR"].values, T["LIQ"].values
    Cdf = T["C"]
    haut = Cdf.shift(1).rolling(n, min_periods=n).max().values     # plus haute clôture des n jours précédents
    bas = Cdf.shift(1).rolling(n, min_periods=n).min().values
    jours, syms = T["jours"], T["syms"]
    nj, ns = O.shape
    pos, trades, attente = {}, [], []

    def sortir(s, i, prix, motif):
        p = pos.pop(s)
        d = p["d"]
        dist = p["dist"]
        brut = d * (prix - p["e"]) / dist
        frais = FRAIS_TAKER * (p["e"] + prix) / dist
        nb = max(1, i - p["i"])
        funding = FUNDING_JOUR * nb * p["e"] / dist if d == 1 else 0.0
        trades.append(dict(symbol=syms[s], sens="LONG" if d == 1 else "SHORT",
                           t_entree=jours[p["i"]], t_sortie=jours[i], jours=nb,
                           entree=p["e"], sortie=prix, stop_initial=p["e"] - d * dist,
                           dist_pct=100 * dist / p["e"], R_brut=brut, frais_R=frais, funding_R=funding,
                           R_net=brut - frais - funding, mfe_R=p["mfe"], motif=motif))

    for i in range(nj):
        # 1) entrées décidées la veille, exécutées à l'ouverture
        for s, d, a in attente:
            if len(pos) >= max_pos:
                break
            o = O[i, s]
            if s in pos or not np.isfinite(o):
                continue
            e = o * (1 + d * SLIP_ENTREE)
            dist = k * a
            if dist <= 0 or dist >= e:
                continue
            pos[s] = dict(d=d, e=e, dist=dist, stop=e - d * dist, ext=e, i=i, mfe=0.0)
        attente = []

        # 2) gestion des positions ouvertes sur la bougie du jour
        for s in list(pos):
            p = pos[s]
            o, h, l, c = O[i, s], H[i, s], L[i, s], C[i, s]
            if not np.isfinite(c):
                continue
            d, st = p["d"], p["stop"]
            if d == 1:
                if p["i"] != i and o <= st:
                    sortir(s, i, o * (1 - SLIP_STOP), "stop (ouverture en gap)"); continue
                if l <= st:
                    sortir(s, i, st * (1 - SLIP_STOP), "stop"); continue
                p["mfe"] = max(p["mfe"], (h - p["e"]) / p["dist"])
                p["ext"] = max(p["ext"], c)
                if np.isfinite(A[i, s]):
                    p["stop"] = max(st, p["ext"] - k * A[i, s])
            else:
                if p["i"] != i and o >= st:
                    sortir(s, i, o * (1 + SLIP_STOP), "stop (ouverture en gap)"); continue
                if h >= st:
                    sortir(s, i, st * (1 + SLIP_STOP), "stop"); continue
                p["mfe"] = max(p["mfe"], (p["e"] - l) / p["dist"])
                p["ext"] = min(p["ext"], c)
                if np.isfinite(A[i, s]):
                    p["stop"] = min(st, p["ext"] + k * A[i, s])

        # 3) signaux à la clôture du jour, pour une entrée demain (les plus liquides d'abord)
        if i < nj - 1:
            ok = np.isfinite(haut[i]) & np.isfinite(A[i]) & (LIQ[i] >= LIQ_MIN)
            long_ = ok & (C[i] > haut[i])
            short = ok & (C[i] < bas[i])
            cand = [(LIQ[i, s], s, 1 if long_[s] else -1, A[i, s])
                    for s in np.where(long_ | short)[0] if s not in pos]
            cand.sort(reverse=True)
            attente = [(s, d, a) for _, s, d, a in cand]

    # positions encore ouvertes : valorisées à la dernière clôture connue
    for s in list(pos):
        col = C[:, s]
        dernier = np.where(np.isfinite(col))[0][-1]
        sortir(s, dernier, col[dernier], "encore ouvert (valorisé)")
    tr = pd.DataFrame(trades)
    if len(tr):
        tr = tr.sort_values("t_sortie").reset_index(drop=True)
        for c in ("t_entree", "t_sortie"):
            tr[c] = pd.to_datetime(tr[c], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    return tr


# ---------------- STATISTIQUES ----------------
def resume(tr):
    if not len(tr):
        return dict(n=0, taux=np.nan, moy=np.nan, total=0.0, dd=0.0, top5=np.nan, duree=np.nan, serie=0)
    r = tr.R_net.values
    cum = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]).max())
    pertes, serie = 0, 0
    for x in r:
        pertes = pertes + 1 if x <= 0 else 0
        serie = max(serie, pertes)
    top5 = float(np.sort(r)[-5:].sum())
    return dict(n=len(r), taux=100 * (r > 0).mean(), moy=r.mean(), total=r.sum(), dd=dd,
                top5=top5, duree=float(tr.jours.median()), serie=serie)


def ligne(nom, tr):
    s = resume(tr)
    if not s["n"]:
        return f"| {nom} | 0 | — | — | — | — | — |"
    return (f"| {nom} | {s['n']} | {s['taux']:.0f} % | {s['moy']:+.2f} | {s['total']:+.1f} | "
            f"{s['dd']:.1f} | {s['duree']:.0f} j |")


ENTETE = ("| | Trades | Gagnants | R net moyen | R net total | Pire creux (R) | Durée médiane |\n"
          "|---|---|---|---|---|---|---|")


def rapport(T, source, max_pos):
    jours = T["jours"]
    fmt = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    out = [f"# 🌊 Backtest Marée v{VERSION} — suivi de tendance journalier\n",
           f"_Historique : du {fmt(jours[0])} au {fmt(jours[-1])} ({len(jours)} jours) — {len(T['syms'])} paires — "
           f"source {source}._\n",
           f"_Règles : cassure du plus haut / plus bas de N jours en clôture, stop suiveur à {K_ATR:g} ATR({ATR_N}), "
           f"pas de TP, {max_pos} positions au maximum, volume moyen 30 j ≥ {LIQ_MIN/1e6:.0f} M USDT._\n",
           f"_Coûts : frais {FRAIS_TAKER*100:.2f} % par côté, glissement {SLIP_ENTREE*100:.1f} % à l'entrée et "
           f"{SLIP_STOP*100:.1f} % au stop, funding {FUNDING_JOUR*100:.2f} % par jour payé par les LONG._\n",
           "_Limite : paires cotées aujourd'hui uniquement (les paires disparues manquent)._\n"]

    resultats = {n: backtest(T, n, max_pos=max_pos) for n in N_ROBUSTESSE}
    tr = resultats[N_PRINCIPAL]

    out.append(f"\n## Réglage principal : N = {N_PRINCIPAL} jours\n")
    verdict = "aucun trade"
    if len(tr):
        s = resume(tr)
        milieu = tr.t_entree.sort_values().iloc[len(tr) // 2]
        m1, m2 = tr[tr.t_entree < milieu], tr[tr.t_entree >= milieu]
        r1, r2 = resume(m1), resume(m2)
        gagn = tr[tr.R_net > 0].R_net
        perd = tr[tr.R_net <= 0].R_net
        out += [ENTETE, ligne("Ensemble", tr), ligne("LONG", tr[tr.sens == "LONG"]),
                ligne("SHORT", tr[tr.sens == "SHORT"]),
                f"\n- Gain moyen d'un gagnant : **{gagn.mean():+.2f} R** — perte moyenne d'un perdant : "
                f"**{perd.mean():+.2f} R**",
                f"- Meilleur trade : {tr.R_net.max():+.1f} R — les 5 meilleurs trades font {s['top5']:+.1f} R "
                f"sur un total de {s['total']:+.1f} R",
                f"- Plus longue série de pertes d'affilée : {s['serie']} trades — pire creux : {s['dd']:.1f} R "
                f"(≈ {s['dd'] * RISQUE:.0f} USDT avec {RISQUE:g} USDT de risque)",
                f"- Stop initial : distance médiane {tr.dist_pct.median():.0f} % du prix — "
                f"frais + funding moyens : {(tr.frais_R + tr.funding_R).mean():.2f} R par trade",
                f"- Position type : {RISQUE / (tr.dist_pct.median() / 100):.0f} USDT de valeur pour {RISQUE:g} USDT de risque",
                "\n### Les deux moitiés de l'historique (le test qui compte)\n", ENTETE,
                ligne(f"1re moitié (entrées avant le {milieu})", m1),
                ligne(f"2e moitié (entrées à partir du {milieu})", m2),
                "\n### Par année d'entrée\n", ENTETE]
        for an, g in tr.groupby(tr.t_entree.str[:4]):
            out.append(ligne(an, g))
        out += ["\n### Par année et par sens\n", ENTETE]
        for (an, sens), g in tr.groupby([tr.t_entree.str[:4], "sens"]):
            out.append(ligne(f"{an} · {sens}", g))
        positif = r1["n"] >= 20 and r2["n"] >= 20 and r1["moy"] > 0 and r2["moy"] > 0
        robuste = all(len(resultats[n]) and resultats[n].R_net.mean() > 0 for n in N_ROBUSTESSE)
        if positif and robuste:
            verdict = ("✅ POSITIF sur les deux moitiés, et pour les trois valeurs de N : "
                       "le principe mérite d'être suivi en réel (petit risque).")
        elif positif:
            verdict = ("🟡 POSITIF sur les deux moitiés avec N = 50, mais pas pour toutes les valeurs de N : "
                       "résultat fragile, à regarder de près avant d'aller plus loin.")
        else:
            verdict = "❌ NÉGATIF ou instable : le réglage principal ne tient pas sur les deux moitiés. On n'y va pas."
        out.append(f"\n## Verdict\n\n**{verdict}**\n")
    else:
        out.append("Aucun trade.")

    out += ["\n## Robustesse : même stratégie avec d'autres valeurs de N\n",
            "_Affiché pour vérifier que le résultat ne dépend pas d'un chiffre précis, pas pour choisir le meilleur._\n",
            ENTETE]
    for n in N_ROBUSTESSE:
        out.append(ligne(f"N = {n} jours" + (" (principal)" if n == N_PRINCIPAL else ""), resultats[n]))

    if len(tr):
        out += ["\n## Les 10 meilleurs et les 10 pires trades (N = 50)\n",
                "| Paire | Sens | Entrée | Sortie | Jours | R net |", "|---|---|---|---|---|---|"]
        tri = tr.sort_values("R_net", ascending=False)
        for _, x in pd.concat([tri.head(10), tri.tail(10)]).iterrows():
            out.append(f"| {x.symbol} | {x.sens} | {x.t_entree} | {x.t_sortie} | {x.jours} | {x.R_net:+.1f} |")
        tr.to_csv("maree_trades.csv", index=False)

    with open("maree_stats.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print("\n================ RÉSUMÉ ================")
    for n in N_ROBUSTESSE:
        s = resume(resultats[n])
        if s["n"]:
            print(f"N = {n:>3} : {s['n']} trades | {s['taux']:.0f} % gagnants | {s['moy']:+.2f} R net/trade | "
                  f"total {s['total']:+.1f} R | pire creux {s['dd']:.1f} R")
    print(f"Verdict (N = {N_PRINCIPAL}) : {verdict}")
    print("Rapport complet : maree_stats.md — détail : maree_trades.csv")


def main():
    ap = argparse.ArgumentParser(description="Backtest Marée (suivi de tendance journalier)")
    ap.add_argument("--jours", type=int, default=1500, help="profondeur de l'historique (défaut 1500 jours)")
    ap.add_argument("--paires", type=int, default=100, help="nb de paires, les plus liquides aujourd'hui")
    ap.add_argument("--max-pos", type=int, default=MAX_POS, help="positions ouvertes au maximum")
    ap.add_argument("--retelecharger", action="store_true")
    a = ap.parse_args()
    print(f"BACKTEST MARÉE v{VERSION} — {a.jours} jours, {a.paires} paires, {a.max_pos} positions max")
    sauve = charger_donnees(a.jours, a.paires, a.retelecharger)
    if not sauve["data"]:
        sys.exit("⛔ Aucune donnée journalière récupérée.")
    print(f"{len(sauve['data'])} paires chargées. Calcul…")
    rapport(tableaux(sauve["data"]), sauve.get("source", "?"), a.max_pos)


if __name__ == "__main__":
    main()
