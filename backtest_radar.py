# ==============================================================================
#  BACKTEST DU RADAR ALT V2 — rejoue radar_alt.py sur l'historique Zoomex
#
#  Le backtest appelle les VRAIES fonctions du radar (mesures, detecter, nouveaux_signaux,
#  retenir, ticket) à chaque clôture H4 : ce qui est mesuré ici est ce qui tourne en réel.
#
#  Usage :
#     python backtest_radar.py              # ~400 jours, télécharge puis met en cache
#     python backtest_radar.py --jours 200  # historique plus court
#     python backtest_radar.py --maj        # force un nouveau téléchargement
#
#  Hypothèses : entrée à la clôture H4 du signal ; SL prioritaire si SL et objectif sont
#  touchés dans la même bougie H1 ; clôture au prix du moment à la durée maximale ;
#  frais taker (0,06 %) + glissement (0,02 %) comptés à l'entrée et à la sortie.
#
#  Limites à garder en tête :
#   - l'univers est celui des paires liquides AUJOURD'HUI (les paires disparues manquent) ;
#   - un seul historique d'environ 13 mois, donc peu de régimes de marché différents ;
#   - le financement (funding) n'est pas compté.
#
#  Référence V1 (mêmes données, mêmes frais, objectif 2 R / 72 h) : continuation −0,01 R,
#  retournement −0,17 R par déclenchement, sur ~1 400 déclenchements LONG.
# ==============================================================================
import os, sys, time
import concurrent.futures as cf

import numpy as np
import pandas as pd
import requests

import radar_alt as R

H1, H4, JOUR = R.H1, R.H4, R.JOUR
CACHE = ".cache_radar"
GLISSEMENT = 0.0002
COUPURE = 0.55                 # part de l'historique dans la « 1re moitié » (réglages) / le reste (contrôle)


def telecharger(sym, debut, fin):
    out, end, s = [], fin, requests.Session()
    while end > debut:
        j = None
        for essai in range(4):
            try:
                j = s.get(R.BASE + "kline", params=dict(category="linear", symbol=sym, interval="60",
                                                        limit=1000, end=end), timeout=20).json()
                if j.get("retCode") == 0:
                    break
            except Exception:
                j = None
            time.sleep(1 + essai)
        if not j or j.get("retCode") != 0:
            return None
        lot = j["result"]["list"]
        if not lot:
            break
        out += lot
        premier = min(int(x[0]) for x in lot)
        if len(lot) < 1000 or premier >= end:
            break
        end = premier - 1
    if not out:
        return None
    d = pd.DataFrame(out).iloc[:, :7]
    d.columns = ["t", "o", "h", "l", "c", "v", "q"]
    d = d.astype(float).drop_duplicates("t").sort_values("t")
    return d[(d.t >= debut) & (d.t + H1 <= fin)].reset_index(drop=True)


def donnees(jours, maj):
    os.makedirs(CACHE, exist_ok=True)
    fichiers = [f for f in os.listdir(CACHE) if f.endswith(".pkl")]
    if fichiers and not maj:
        print(f"Cache : {len(fichiers)} paires dans {CACHE}/ (--maj pour retélécharger)")
        return {f[:-4]: pd.read_pickle(os.path.join(CACHE, f)) for f in sorted(fichiers)}
    fin = int(time.time() * 1000) // H1 * H1
    res = R.api("tickers", category="linear")
    if not res:
        sys.exit("⛔ Données Zoomex inaccessibles.")
    df = pd.DataFrame(res["list"])
    df["turnover24h"] = pd.to_numeric(df.turnover24h, errors="coerce")
    df = df[df.symbol.str.endswith("USDT")].sort_values("turnover24h", ascending=False)
    info = R.instruments()
    syms = [s for s in df.symbol.head(220) if s == "BTCUSDT" or R.est_crypto(s, info)][:160]
    print(f"Téléchargement de {len(syms)} paires sur {jours} jours…")
    out = {}
    with cf.ThreadPoolExecutor(6) as ex:
        for sym, d in zip(syms, ex.map(lambda s: telecharger(s, fin - jours * JOUR, fin), syms)):
            if d is not None and len(d) > 600:
                d.to_pickle(os.path.join(CACHE, sym + ".pkl"))
                out[sym] = d
    return out


def regrouper(d, duree):
    g = d.groupby(d.t // duree)
    return pd.DataFrame(dict(t=g.t.first() // duree * duree, o=g.o.first(), h=g.h.max(), l=g.l.min(),
                             c=g.c.last(), v=g.v.sum())).reset_index(drop=True)


def resultat(h1, k, sens, e, sl, tp):
    """Résultat net en R d'une entrée à la clôture de la bougie H1 d'indice k."""
    risque = abs(e - sl)
    cout = 2 * (R.FRAIS_TAKER + GLISSEMENT) * e / risque
    fin = min(len(h1["t"]), k + 1 + R.SUIVI_MAX_H)
    if fin - (k + 1) < R.SUIVI_MAX_H:
        return None                                        # pas assez de recul : signal encore ouvert
    hh, ll = h1["h"][k + 1:fin], h1["l"][k + 1:fin]
    pire, mieux = (ll, hh) if sens == 1 else (hh, ll)
    for n in range(len(hh)):
        if sens * (pire[n] - sl) <= 0:
            return "SL", -1.0 - cout
        if sens * (mieux[n] - tp) >= 0:
            return "OBJECTIF", R.OBJECTIF_R - cout
    return "EXPIRE", sens * (h1["c"][fin - 1] - e) / risque - cout


def rejouer(D, limite=True):
    S = {}
    for sym, d in D.items():
        if sym == "BTCUSDT":
            continue
        h4, dj = regrouper(d, H4), regrouper(d, JOUR)
        S[sym] = dict(h4=h4, t4=h4.t.values, d=dj, td=dj.t.values, t1=d.t.values,
                      h1={c: d[c].values for c in "thlc"}, q24=d.q.rolling(24).sum().values)
    t_min = min(s["t1"][0] for s in S.values())
    t_max = max(s["t1"][-1] for s in S.values()) + H1
    blocs = np.arange((t_min // H4 + R.BARRES_30J + 2) * H4, t_max + 1, H4)
    vus, premier, signaux = {}, True, []
    for bloc in blocs:
        vol = {}
        for sym, s in S.items():
            k = int(np.searchsorted(s["t1"], bloc - H1))
            if k < len(s["t1"]) and s["t1"][k] == bloc - H1 and s["q24"][k] >= R.LIQ_MIN:
                vol[sym] = (s["q24"][k], k)
        univers = sorted(vol, key=lambda x: -vol[x][0])[:R.PAIRES_MAX]
        M = {}
        for sym in univers:
            s = S[sym]
            i = int(np.searchsorted(s["t4"], bloc - H4, side="right"))
            j = int(np.searchsorted(s["td"], bloc - JOUR, side="right"))
            m = R.mesures(s["h4"].iloc[max(0, i - R.BARRES_BAS - 40):i], s["d"].iloc[max(0, j - 120):j])
            if m and m["t"] == bloc:
                M[sym] = m
        if not M:
            continue
        neufs = R.nouveaux_signaux(R.detecter(M), vus, bloc)
        if premier:
            premier = False
            continue                                       # amorçage, comme en réel
        volume = {s: vol[s][0] for s in M}
        for sym, typ in (R.retenir(neufs, volume) if limite else neufs):
            m = M[sym]
            e, sl, tp = R.ticket(m["prix"], m["atr"], typ)
            res = resultat(S[sym]["h1"], vol[sym][1], R.SENS[typ], e, sl, tp)
            if res:
                signaux.append(dict(sym=sym, type=typ, t=bloc, statut=res[0], R=res[1]))
    T = pd.DataFrame(signaux)
    T["date"] = pd.to_datetime(T.t, unit="ms")
    return T


def ligne(x):
    if not len(x):
        return "aucun signal"
    sem = max(1.0, (x.t.max() - x.t.min()) / (7 * JOUR))
    return (f"{len(x):4d} signaux ({len(x) / sem:4.1f}/sem) · gagnants {100 * (x.R > 0).mean():3.0f} % · "
            f"objectif {100 * (x.statut == 'OBJECTIF').mean():3.0f} % · SL {100 * (x.statut == 'SL').mean():3.0f} % · "
            f"moyenne {x.R.mean():+.2f} R · total {x.R.sum():+6.1f} R")


def rapport(T, titre):
    coupure = T.t.min() + COUPURE * (T.t.max() - T.t.min())
    print(f"\n===== {titre} — du {T.date.min():%d/%m/%Y} au {T.date.max():%d/%m/%Y} =====")
    for typ in list(R.SENS) + [None]:
        x = T if typ is None else T[T.type == typ]
        print(f"\n{(typ or 'ENSEMBLE').upper()}")
        print("  tout       :", ligne(x))
        print("  1re moitié :", ligne(x[x.t < coupure]))
        print("  2e moitié  :", ligne(x[x.t >= coupure]))
    mois = T.groupby([T.date.dt.to_period("M"), "type"]).R.agg(["size", "sum"]).unstack().fillna(0)
    print("\nPar mois (nombre de signaux, total en R) :")
    for m, r in mois.iterrows():
        print(f"  {m}  " + "  ".join(f"{t:11s} {int(r[('size', t)]):3d} {r[('sum', t)]:+6.1f} R" for t in R.SENS if ("size", t) in r))
    sem = T.groupby(T.date.dt.to_period("W")).R.sum()
    print(f"\nSemaines positives : {(sem > 0).sum()}/{len(sem)} · pire semaine {sem.min():+.1f} R · "
          f"meilleure {sem.max():+.1f} R")
    cumul = T.sort_values("t").R.cumsum()
    print(f"Pire creux du cumul : {(cumul - cumul.cummax()).min():+.1f} R")


if __name__ == "__main__":
    jours = int(sys.argv[sys.argv.index("--jours") + 1]) if "--jours" in sys.argv else 400
    D = donnees(jours, "--maj" in sys.argv)
    print(f"{len(D)} paires chargées.")
    rapport(rejouer(D, limite=True), f"RADAR ALT V{R.VERSION} (au plus {R.MAX_PAR_PASSAGE} signaux par sens et par H4)")
    if "--sans-limite" in sys.argv:
        rapport(rejouer(D, limite=False), f"RADAR ALT V{R.VERSION} sans limite par passage")
