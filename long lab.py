# ==============================================================================
#  LONG LAB v1.0 — recherche d'une stratégie LONG uniquement (fichier autonome)
#
#  Question posée : existe-t-il une façon d'acheter qui fasse MIEUX que d'acheter au hasard ?
#  Sur 4 ans où le marché a globalement monté, presque n'importe quel achat finit positif.
#  Chaque stratégie est donc comparée à des ENTRÉES AU HASARD (mêmes paires, même stop,
#  même sortie, mêmes coûts) : si elle ne bat pas le hasard, elle ne fait que suivre le marché.
#
#  Les 4 stratégies testées (bougies journalières, LONG uniquement, règles fixées d'avance) :
#    A. Marée long          : clôture au-dessus du plus haut de 50 jours, stop suiveur 3 ATR.
#    B. Marée long + BTC    : comme A, mais seulement quand BTC est au-dessus de sa moyenne 200 jours.
#    C. Leaders             : chaque dimanche soir, si BTC est au-dessus de sa moyenne 200 jours,
#                             achat des 5 paires les plus fortes sur 30 jours ; stop suiveur 3 ATR.
#    D. Repli en tendance   : paire au-dessus de sa moyenne 100 jours, BTC au-dessus de sa moyenne
#                             200 jours, 3 clôtures en baisse d'affilée -> achat ; sortie dès qu'une
#                             clôture dépasse le plus haut de la veille, ou après 7 jours ;
#                             stop fixe à 2,5 ATR.
#
#  Une stratégie est retenue seulement si elle remplit les TROIS conditions :
#    1. au moins 100 trades ;
#    2. R net moyen positif sur CHACUNE des deux moitiés de l'historique ;
#    3. elle fait mieux que 95 % des tirages d'entrées au hasard.
#  Attention : avec 4 stratégies testées, l'une peut passer par chance. Une stratégie retenue
#  ici mérite un suivi réel à petit risque, pas une confiance aveugle.
#
#  Mêmes coûts que le backtest Marée : frais 0,06 % par côté, glissement 0,5 % à l'entrée et
#  0,2 % à la sortie, funding 0,03 % par jour. Entrée le lendemain du signal, à l'ouverture.
#
#  Utilisation (Colab) :  !python long_lab.py
#  Réutilise les données déjà téléchargées par maree_backtest.py si elles sont là.
#  Résultats : long_lab_stats.md et long_lab_trades.csv.
# ==============================================================================
import argparse, os, pickle, sys, time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

VERSION = "1.0"

ATR_N        = 20
LIQ_MIN      = 10_000_000
MAX_POS      = 10
RISQUE       = 1.0
FRAIS_TAKER  = 0.0006
SLIP_ENTREE  = 0.005
SLIP_SORTIE  = 0.002
FUNDING_JOUR = 0.0003
TIRAGES      = 200            # nb de tirages d'entrées au hasard par stratégie
SEUIL_HASARD = 95             # % de tirages à battre

JOUR = 86_400_000
SOURCES = {"Zoomex": "https://openapi.zoomex.com/cloud/trade/v3/market/",
           "Bybit":  "https://api.bybit.com/v5/market/"}
SRC = None
SESS = requests.Session()


# ---------------- TÉLÉCHARGEMENT (identique à maree_backtest.py) ----------------
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
    return df[df.t + JOUR <= fin].reset_index(drop=True)


def charger_donnees(jours, npaires, forcer):
    fichier = f"maree_data_{jours}j_{npaires}p.pkl"
    if os.path.exists(fichier) and not forcer:
        with open(fichier, "rb") as f:
            sauve = pickle.load(f)
        print(f"Données reprises de {fichier}")
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
    def tab(col):
        return pd.DataFrame({s: d.set_index("t")[col] for s, d in data.items()}).sort_index()
    O, H, L, C, TO = tab("o"), tab("h"), tab("l"), tab("c"), tab("to")
    prec = C.shift(1)
    tr = pd.concat([H - L, (H - prec).abs(), (L - prec).abs()]).groupby(level=0).max()
    atr = tr.ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean()
    liq = TO.rolling(30, min_periods=30).mean()
    if "BTCUSDT" not in C:
        sys.exit("⛔ BTCUSDT absent des données : impossible de calculer le régime BTC.")
    btc = C["BTCUSDT"]
    regime = (btc > btc.rolling(200, min_periods=200).mean()).fillna(False).values
    return dict(O=O, H=H, L=L, C=C, ATR=atr, LIQ=liq, regime=regime,
                jours=O.index.values, syms=list(O.columns))


def signaux(T):
    """Les 4 signaux d'achat, calculés à la clôture de chaque jour (aucune donnée du futur)."""
    C, H, A, LIQ = T["C"], T["H"], T["ATR"], T["LIQ"]
    ok = (A.notna() & (LIQ >= LIQ_MIN)).values
    reg = T["regime"][:, None]
    c = C.values

    haut50 = C.shift(1).rolling(50, min_periods=50).max().values
    with np.errstate(invalid="ignore"):
        cassure = ok & (c > haut50)

        perf30 = (C / C.shift(30) - 1).values
        dimanche = (pd.to_datetime(T["jours"], unit="ms", utc=True).dayofweek == 6)[:, None]
        p = np.where(ok & (perf30 > 0), perf30, -np.inf)
        rang = (-p).argsort(axis=1).argsort(axis=1)
        leaders = ok & reg & dimanche & (rang < 5) & np.isfinite(p)

        m100 = C.rolling(100, min_periods=100).mean().values
        baisse = (C < C.shift(1)) & (C.shift(1) < C.shift(2)) & (C.shift(2) < C.shift(3))
        repli = ok & reg & (c > m100) & baisse.values

    liq = np.nan_to_num(LIQ.values, nan=0.0)
    return {
        "A": dict(nom="A. Marée long", sig=cassure, prio=liq, k=3.0, sortie="suiveur", eligible=ok),
        "B": dict(nom="B. Marée long + BTC haussier", sig=cassure & reg, prio=liq, k=3.0, sortie="suiveur",
                  eligible=ok & reg),
        "C": dict(nom="C. Leaders (5 plus fortes, chaque semaine)", sig=leaders,
                  prio=np.nan_to_num(perf30, nan=-9.0), k=3.0, sortie="suiveur", eligible=ok & reg & dimanche),
        "D": dict(nom="D. Repli en tendance haussière", sig=repli, prio=liq, k=2.5, sortie="rebond",
                  eligible=ok & reg),
    }


# ---------------- MOTEUR (LONG uniquement) ----------------
def moteur(T, sig, prio, k, sortie, max_pos=MAX_POS, duree_max=7, detail=False):
    """sortie = "suiveur" : stop suiveur à k ATR sous la plus haute clôture depuis l'entrée.
    sortie = "rebond"  : stop fixe à k ATR ; sortie à l'ouverture du lendemain d'une clôture
                         au-dessus du plus haut de la veille, ou après duree_max jours."""
    O, H, L, C, A = T["O"].values, T["H"].values, T["L"].values, T["C"].values, T["ATR"].values
    nj = O.shape[0]
    pos, out, attente = {}, [], []

    def sortir(s, i, prix, motif):
        p = pos.pop(s)
        dist = p["dist"]
        brut = (prix - p["e"]) / dist
        nb = max(1, i - p["i"])
        couts = FRAIS_TAKER * (p["e"] + prix) / dist + FUNDING_JOUR * nb * p["e"] / dist
        out.append((s, p["i"], i, nb, p["e"], prix, 100 * dist / p["e"], brut - couts, motif))

    for i in range(nj):
        for s in list(pos):                                   # sorties programmées la veille
            if pos[s].get("sortir") and np.isfinite(O[i, s]):
                sortir(s, i, O[i, s] * (1 - SLIP_SORTIE), pos[s]["sortir"])
        for s, a in attente:                                  # entrées décidées la veille
            if len(pos) >= max_pos:
                break
            o = O[i, s]
            if s in pos or not np.isfinite(o):
                continue
            e = o * (1 + SLIP_ENTREE)
            dist = k * a
            if dist <= 0 or dist >= e:
                continue
            pos[s] = dict(e=e, dist=dist, stop=e - dist, ext=e, i=i)
        attente = []

        for s in list(pos):
            p = pos[s]
            o, h, l, c = O[i, s], H[i, s], L[i, s], C[i, s]
            if not np.isfinite(c):
                continue
            st = p["stop"]
            if p["i"] != i and o <= st:
                sortir(s, i, o * (1 - SLIP_SORTIE), "stop (gap)"); continue
            if l <= st:
                sortir(s, i, st * (1 - SLIP_SORTIE), "stop"); continue
            if sortie == "suiveur":
                p["ext"] = max(p["ext"], c)
                if np.isfinite(A[i, s]):
                    p["stop"] = max(st, p["ext"] - k * A[i, s])
            else:
                if i > 0 and c > H[i - 1, s]:
                    p["sortir"] = "rebond"
                elif i - p["i"] + 1 >= duree_max:
                    p["sortir"] = "durée max"

        if i < nj - 1:
            idx = np.where(sig[i])[0]
            if len(idx):
                idx = idx[np.argsort(-prio[i, idx], kind="stable")]
                attente = [(s, A[i, s]) for s in idx if s not in pos]

    for s in list(pos):
        col = C[:, s]
        dernier = np.where(np.isfinite(col))[0][-1]
        sortir(s, dernier, col[dernier], "encore ouvert (valorisé)")
    if not detail:
        return np.array([x[7] for x in out]), np.array([x[1] for x in out])
    tr = pd.DataFrame(out, columns=["s", "i_e", "i_s", "jours", "entree", "sortie", "dist_pct", "R_net", "motif"])
    jours = T["jours"]
    f = lambda idx: pd.to_datetime(jours[idx], unit="ms", utc=True).strftime("%Y-%m-%d")
    tr["symbol"] = [T["syms"][s] for s in tr.s]
    tr["t_entree"], tr["t_sortie"] = f(tr.i_e.values), f(tr.i_s.values)
    return tr.sort_values("i_s").reset_index(drop=True)


def hasard(T, st, graine):
    """Mêmes règles de stop / sortie / coûts, mais achats tirés au hasard parmi les cases
    (jour, paire) où la stratégie avait le droit d'acheter. Autant de signaux que la vraie."""
    rng = np.random.default_rng(graine)
    cases = np.flatnonzero(st["eligible"])
    n = int(st["sig"].sum())
    if not len(cases) or not n:
        return np.nan
    tir = np.zeros(st["sig"].size, dtype=bool)
    tir[rng.choice(cases, size=min(n, len(cases)), replace=False)] = True
    r, _ = moteur(T, tir.reshape(st["sig"].shape), rng.random(st["sig"].shape), st["k"], st["sortie"])
    return r.mean() if len(r) else np.nan


# ---------------- RAPPORT ----------------
def creux(r):
    cum = np.r_[0, np.cumsum(r)]
    return float((np.maximum.accumulate(cum) - cum).max())


def stats(tr):
    if not len(tr):
        return "0 | — | — | — | — | —"
    r = tr.R_net.values
    return (f"{len(r)} | {100 * (r > 0).mean():.0f} % | {r.mean():+.2f} | {r.sum():+.1f} | "
            f"{creux(r):.1f} | {tr.jours.median():.0f} j")


ENTETE = ("| | Trades | Gagnants | R net moyen | R net total | Pire creux (R) | Durée médiane |\n"
          "|---|---|---|---|---|---|---|")


def analyser(T, source, tirages):
    S = signaux(T)
    jours = T["jours"]
    fmt = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    out = [f"# 🧪 Long Lab v{VERSION} — quatre stratégies LONG contre le hasard\n",
           f"_Historique : du {fmt(jours[0])} au {fmt(jours[-1])} ({len(jours)} jours) — {len(T['syms'])} paires — "
           f"source {source}._\n",
           f"_BTC au-dessus de sa moyenne 200 jours : {100 * T['regime'].mean():.0f} % des jours "
           "(les 200 premiers jours ne comptent pas, faute d'historique)._\n",
           f"_Hasard : {tirages} tirages par stratégie, mêmes paires éligibles, même stop, même sortie, mêmes coûts._\n",
           "\n## Tableau de synthèse\n",
           "| Stratégie | Trades | R net moyen | 1re moitié | 2e moitié | Hasard (moyenne) | Tirages battus | Retenue ? |",
           "|---|---|---|---|---|---|---|---|"]
    details, resume, tous = [], [], []
    for cle, st in S.items():
        t0 = time.time()
        tr = moteur(T, st["sig"], st["prio"], st["k"], st["sortie"], detail=True)
        if not len(tr):
            out.append(f"| {st['nom']} | 0 | — | — | — | — | — | ❌ |")
            resume.append(f"{st['nom']} : aucun trade")
            continue
        r = tr.R_net.values
        milieu = np.sort(tr.i_e.values)[len(tr) // 2]
        m1, m2 = tr[tr.i_e < milieu], tr[tr.i_e >= milieu]
        tir = np.array([hasard(T, st, g) for g in range(tirages)])
        tir = tir[np.isfinite(tir)]
        battus = 100 * (r.mean() > tir).mean() if len(tir) else np.nan
        ok = len(r) >= 100 and len(m1) and len(m2) and m1.R_net.mean() > 0 and m2.R_net.mean() > 0 \
            and battus >= SEUIL_HASARD
        out.append(f"| {st['nom']} | {len(r)} | {r.mean():+.2f} | {m1.R_net.mean():+.2f} | {m2.R_net.mean():+.2f} | "
                   f"{tir.mean():+.2f} | {battus:.0f} % | {'✅ oui' if ok else '❌ non'} |")
        resume.append(f"{st['nom']} : {len(r)} trades | {r.mean():+.2f} R net/trade | moitiés {m1.R_net.mean():+.2f} / "
                      f"{m2.R_net.mean():+.2f} | hasard {tir.mean():+.2f} | bat {battus:.0f} % des tirages | "
                      f"{'RETENUE' if ok else 'non retenue'}")
        d = [f"\n## {st['nom']}\n", ENTETE, f"| Ensemble | {stats(tr)} |",
             f"| 1re moitié | {stats(m1)} |", f"| 2e moitié | {stats(m2)} |"]
        for an, g in tr.groupby(tr.t_entree.str[:4]):
            d.append(f"| {an} | {stats(g)} |")
        top5 = float(np.sort(r)[-5:].sum())
        d.append(f"\n- Les 5 meilleurs trades : {top5:+.1f} R sur un total de {r.sum():+.1f} R — "
                 f"stop médian à {tr.dist_pct.median():.0f} % du prix")
        d.append(f"- Entrées au hasard : {tir.mean():+.2f} R net par trade en moyenne ; "
                 f"les 5 % meilleurs tirages dépassent {np.percentile(tir, 95):+.2f} R")
        details += d
        tr.insert(0, "strategie", cle)
        tous.append(tr.drop(columns=["s", "i_e", "i_s"]))
        print(f"  {st['nom']} : fait ({time.time() - t0:.0f} s)", flush=True)

    out += ["\n_« Tirages battus » : part des tirages au hasard qui font moins bien que la stratégie. "
            f"En dessous de {SEUIL_HASARD} %, la stratégie ne se distingue pas d'achats au hasard sur la même période._\n"]
    with open("long_lab_stats.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out + details) + "\n")
    if tous:
        pd.concat(tous).to_csv("long_lab_trades.csv", index=False)
    print("\n================ RÉSUMÉ ================")
    for ligne in resume:
        print(ligne)
    print("Rapport complet : long_lab_stats.md — détail : long_lab_trades.csv")


def main():
    ap = argparse.ArgumentParser(description="Long Lab : stratégies LONG contre le hasard")
    ap.add_argument("--jours", type=int, default=1500)
    ap.add_argument("--paires", type=int, default=100)
    ap.add_argument("--tirages", type=int, default=TIRAGES)
    ap.add_argument("--retelecharger", action="store_true")
    a = ap.parse_args()
    print(f"LONG LAB v{VERSION} — {a.jours} jours, {a.paires} paires, {a.tirages} tirages au hasard par stratégie")
    sauve = charger_donnees(a.jours, a.paires, a.retelecharger)
    if not sauve["data"]:
        sys.exit("⛔ Aucune donnée journalière récupérée.")
    print(f"{len(sauve['data'])} paires chargées. Calcul (2 à 4 minutes)…")
    analyser(tableaux(sauve["data"]), sauve.get("source", "?"), a.tirages)


if __name__ == "__main__":
    main()
