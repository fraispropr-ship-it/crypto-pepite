# ==============================================================================
#  BACKTEST CRYPTO PÉPITE — rejoue crypto_pepite.py (V6.3) sur l'historique
#
#  Principe : le script importe TON scanner et appelle ses propres fonctions
#  (analyse, zones, bougie de rejet, score, filtre BTC, suivi TP/SL, simulation
#  des sorties, statistiques). Seules les bougies sont remplacées : à chaque pas
#  de 15 min, le scanner ne voit que les bougies DÉJÀ CLÔTURÉES à ce moment-là.
#
#  Utilisation (Colab ou PC, crypto_pepite.py dans le même dossier) :
#     python backtest_pepite.py --jours 7  --paires 20    # essai rapide
#     python backtest_pepite.py --jours 60 --paires 60    # vrai test
#
#  Résultats : backtest_stats.md (même présentation que ton journal)
#              backtest_journal.csv (tous les signaux, une ligne par signal)
#
#  Limites (écrites aussi en tête du rapport) :
#   - OI : pas d'historique -> composante OI du score fixée à 5 (comme « OI n/d »)
#   - funding non pris en compte, spread supposé à 0,05 %
#   - paires = les plus liquides AUJOURD'HUI (biais de survie)
#   - entrée au niveau théorique (sans l'écart de ~0,2 R constaté en réel)
# ==============================================================================
import argparse, math, os, pickle, sys, time
from types import SimpleNamespace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import crypto_pepite as cp

M15, H1, H4 = 900_000, 3_600_000, 14_400_000
DUREE = {"15": M15, "60": H1, "240": H4}
H48 = cp.JOURNAL_EXPIRE_H * H1
SPREAD_SUPPOSE = 0.0005
JOUR = 86_400_000

SOURCES = {"Zoomex": "https://openapi.zoomex.com/cloud/trade/v3/market/",
           "Bybit":  "https://api.bybit.com/v5/market/"}
SRC = None
SESS = requests.Session()
DATA, INFO = {}, {}
NOW = [0]


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
    sys.exit("⛔ Aucune source accessible. Lance le backtest depuis ton PC "
             "(pip install pandas numpy requests, puis python backtest_pepite.py).")


def liste_paires(n):
    res = api("tickers", category="linear")
    df = pd.DataFrame(res["list"])
    for c in ["turnover24h", "bid1Price", "ask1Price", "lastPrice"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df.symbol.str.endswith("USDT")].copy()
    df["spread"] = (df.ask1Price - df.bid1Price) / df.lastPrice
    df = df[(df.turnover24h >= cp.MIN_TURNOVER) & (df.spread <= cp.MAX_SPREAD)]
    syms = list(df.sort_values("turnover24h", ascending=False).symbol.head(n))
    if "BTCUSDT" not in syms:
        syms.append("BTCUSDT")
    return syms


def lire_instruments():
    res = api("instruments-info", category="linear", limit=1000)
    info = {}
    for it in (res if isinstance(res, dict) else {}).get("list", []):
        try:
            info[it["symbol"]] = dict(tick=float(it["priceFilter"]["tickSize"]),
                                      step=float(it["lotSizeFilter"]["qtyStep"]),
                                      minq=float(it["lotSizeFilter"]["minOrderQty"]))
        except Exception:
            pass
    return info


def telecharger(sym, interval, debut, fin):
    lignes, cur = [], fin
    while cur > debut:
        res = api("kline", category="linear", symbol=sym, interval=interval,
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
    return df


def preparer(sym, iv, df):
    d = dict(df=df[["t", "o", "h", "l", "c", "v"]].reset_index(drop=True), t=df.t.values)
    if iv == "15":
        d["c"] = df.c.values
        d["cs"] = np.concatenate([[0.0], np.cumsum(df["to"].fillna(0).values)])
    return d


def charger_donnees(jours, npaires, forcer):
    fichier = f"bt_data_{jours}j_{npaires}p.pkl"
    if os.path.exists(fichier) and not forcer:
        with open(fichier, "rb") as f:
            sauve = pickle.load(f)
        print(f"Données reprises de {fichier} (ajoute --retelecharger pour les rafraîchir)")
        return sauve
    choisir_source()
    fin = int(time.time() * 1000)
    debut = fin - jours * JOUR
    fenetres = {"15": debut - 3 * JOUR, "60": debut - 10 * JOUR, "240": debut - 36 * JOUR}
    syms = liste_paires(npaires)
    info = lire_instruments()
    data = {}
    t0 = time.time()
    for i, sym in enumerate(syms, 1):
        d = {}
        for iv, deb in fenetres.items():
            df = telecharger(sym, iv, deb, fin)
            if df is not None and len(df) >= 60:
                d[iv] = preparer(sym, iv, df)
        if len(d) == 3:
            data[sym] = d
        print(f"  téléchargement {i}/{len(syms)} {sym} ({time.time() - t0:.0f} s)", flush=True)
    sauve = dict(data=data, info=info, debut=debut, fin=fin, source=SRC)
    with open(fichier, "wb") as f:
        pickle.dump(sauve, f)
    return sauve


# ---------------- BRANCHEMENT SUR LE SCANNER ----------------
_kcache = {}


def klines_bt(sym, interval, limit=200):
    """Remplace cp.klines : bougies clôturées à l'instant NOW, comme en direct."""
    d = DATA.get(sym, {}).get(interval)
    if d is None:
        return None
    n = int(np.searchsorted(d["t"], NOW[0] - DUREE[interval], side="right"))
    lo = max(0, n - (limit - 1))
    if n - lo <= 0:
        return None
    k = (sym, interval, lo, n)
    df = _kcache.get(k)
    if df is None:
        if len(_kcache) > 20_000:
            _kcache.clear()
        df = d["df"].iloc[lo:n].reset_index(drop=True)
        _kcache[k] = df
    return df


def memo(fn, cle):
    cache = {}

    def f(*a, **k):
        c = cle(*a, **k)
        v = cache.get(c)
        if v is None:
            if len(cache) > 100_000:
                cache.clear()
            v = fn(*a, **k)
            cache[c] = v
        return v
    return f


def kdf(df):
    return (len(df), df.t.iat[0], df.t.iat[-1], df.c.iat[-1])


def kser(s):
    return (len(s), s.iat[0], s.iat[-1], s.iat[len(s) // 2])


def brancher():
    cp.print = lambda *a, **k: None               # le scanner reste muet pendant le backtest
    cp.oi_change = lambda sym: (None, None)       # pas d'historique d'OI
    cp.klines = klines_bt
    # Mêmes fonctions, simplement mémorisées (les données H1 / H4 ne changent qu'une fois l'heure)
    cp.tendance = memo(cp.tendance, lambda df: kdf(df))
    cp.atr = memo(cp.atr, lambda df, n=14: (kdf(df), n))
    cp.rsi = memo(cp.rsi, lambda c, n=14: (kser(c), n))
    cp.zones = memo(cp.zones, lambda df, a, k=3, lookback=150: (kdf(df), a, k, lookback))
    cp.correlation_btc = memo(cp.correlation_btc, lambda h1: (
        kdf(h1), cp.BTC_CTX["h1"].t.iat[-1] if cp.BTC_CTX else None))


def prix_dans_une_zone(sym):
    """Pré-filtre rapide : sans prix dans la fenêtre d'une zone, analyse() ne renvoie rien."""
    h4, h1, m15 = cp.klines(sym, "240"), cp.klines(sym, "60"), cp.klines(sym, "15")
    if any(x is None or len(x) < 60 for x in (h4, h1, m15)):
        return False
    a1 = cp.atr(h1).iloc[-1]
    px = m15.c.iat[-1]
    zs = cp.zones(h1, a1)
    sup = [z for z in zs if (z["lo"] + z["hi"]) / 2 < px]
    res = [z for z in zs if (z["lo"] + z["hi"]) / 2 >= px]
    if sup:
        z = max(sup, key=lambda z: z["hi"])
        if z["lo"] <= px <= z["hi"] + 0.5 * a1:
            return True
    if res:
        z = min(res, key=lambda z: z["lo"])
        if z["lo"] - 0.5 * a1 <= px <= z["hi"]:
            return True
    return False


# ---------------- SUIVI D'UN SIGNAL (mêmes règles que le journal) ----------------
def tranche(sym, a, b):
    d = DATA[sym]["15"]
    i, k = np.searchsorted(d["t"], a, "left"), np.searchsorted(d["t"], b, "left")
    return d["df"].iloc[i:k]


def couvert(sym, jusqua):
    return DATA[sym]["15"]["t"][-1] >= jusqua - M15


def evaluer(lg):
    """Renvoie (ligne mise à jour, instant où le signal cesse d'être « ouvert »)."""
    sym, ts = lg["symbol"], lg["ts"]
    if lg["statut"] == "EN_COURS":
        t_e = ts
    else:
        if not couvert(sym, ts + H48):
            return lg, math.inf
        p = cp.parcours(lg, tranche(sym, ts, ts + H48), False)
        if p["statut"] in ("INVALIDE", "RATE"):
            lg.update(statut=p["statut"], date_sortie=cp.fmt_date(p["t_sortie"] or ts))
            return lg, p["t_sortie"] or ts
        if not p["actif"]:
            lg.update(statut="NON_DECLENCHE", date_sortie=cp.fmt_date(ts + H48))
            return lg, ts + H48
        t_e = p["t_entree"]
    if not couvert(sym, t_e + H48):
        return lg, math.inf
    bars = tranche(sym, t_e, t_e + H48)
    if not len(bars):
        return lg, math.inf
    p = cp.parcours(lg, bars, True)
    d = 1 if lg["sens"] == "LONG" else -1
    risque = abs(lg["entree"] - lg["sl"])
    if p["statut"] is None:
        statut, r = "EXPIRE", d * (bars.c.iat[-1] - lg["entree"]) / risque
        t_s = bars.t.iat[-1] + M15
    elif p["statut"] in ("TP", "SL"):
        statut, r, t_s = p["statut"], float(p["r"]), p["t_sortie"]
    else:
        lg.update(statut=p["statut"], date_sortie=cp.fmt_date(ts))
        return lg, ts
    frais = lg["frais_R"] if pd.notna(lg["frais_R"]) else 0.0
    lg.update(statut=statut, date_sortie=cp.fmt_date(t_s), ts_entree=t_e,
              resultat_R=round(r, 2), resultat_net_R=round(r - frais, 2),
              mfe_R=round(p["mfe"], 2), mae_R=round(p["mae"], 2),
              duree_h=round((t_s - t_e) / H1, 1), sim_statut="ok")
    for c in cp.SIM_COLS:
        lg[c] = round(cp.rejouer(lg, bars, c), 2)
    return lg, t_s


# ---------------- BOUCLE PRINCIPALE ----------------
def un_pas(T, etat, ouvert_jusqua, dernier_fantome, lignes):
    NOW[0] = T
    cp.BTC_CTX = None
    cp.contexte_btc()

    # Paires liquides à cet instant (volume 24 h reconstitué depuis les bougies M15)
    liq = []
    for sym, d in DATA.items():
        n = int(np.searchsorted(d["15"]["t"], T - M15, side="right"))
        if n < 97:
            continue
        tv = d["15"]["cs"][n] - d["15"]["cs"][n - 96]
        if tv >= cp.MIN_TURNOVER:
            liq.append((tv, sym, d["15"]["c"][n - 1] / d["15"]["c"][n - 97] - 1, d["15"]["c"][n - 1]))
    liq.sort(reverse=True)

    results = []
    for tv, sym, ch24, px in liq[:cp.SHORTLIST]:
        if not prix_dans_une_zone(sym):
            continue
        row = SimpleNamespace(symbol=sym, lastPrice=px, price24hPcnt=ch24, turnover24h=tv,
                              fundingRate=np.nan, spread=SPREAD_SUPPOSE)
        try:
            results.extend(cp.analyse(row, INFO.get(sym, {})))
        except Exception:
            pass
    if not results:
        return

    # ---- Même sélection que scan() ----
    btc_sans_dir = cp.BTC_FILTRE and cp.BTC_CTX is not None and cp.BTC_CTX["n_neutre"] == 2
    score_min = cp.SCORE_MIN_BTC_NEUTRE if btc_sans_dir else cp.SCORE_MIN
    max_now = cp.MAX_NOW_BTC_NEUTRE if btc_sans_dir else cp.MAX_TRADE_NOW

    def tradable(r): return not (cp.SHORT_MODE == "FANTOME" and r["sens"] == "SHORT")
    cle_prio = lambda r: (cp.PRIO[r["decision"]], r["dist"])
    meilleurs = {}
    for r in results:
        if not tradable(r):
            continue
        b = meilleurs.get(r["symbol"])
        if b is None or cle_prio(r) < cle_prio(b):
            meilleurs[r["symbol"]] = r
    tri = (lambda r: -r["score"]) if cp.TRI_PAR_SCORE else cle_prio
    ok = sorted([r for r in meilleurs.values() if r["decision"] != "NO TRADE"], key=tri)
    top = [r for r in ok if r["score"] >= score_min][:cp.MAX_TOP]
    n_now = 0
    for r in top:
        if r["decision"] == "TRADE NOW":
            n_now += 1
            if n_now > max_now:
                r["decision"] = "WAIT"
                r["pourquoi"] = "plafond de TRADE NOW atteint (BTC sans direction) — un seul trade à la fois"

    maintenant = T / 1000
    nouveaux = [r for r in top if r["decision"] == "TRADE NOW"
                and maintenant - etat.get(cp.cle_signal(r), -1e18) > cp.DEDUP_HEURES * 3600]
    cle3 = lambda r: f"{r['symbol']}|{r['sens']}|{r['type']}"

    for r in nouveaux:                                   # trades « réels »
        lg, t_fin = evaluer(cp.ligne_journal(r, maintenant, "REEL", "EN_COURS"))
        lignes.append(lg)
        etat[cp.cle_signal(r)] = maintenant
        ouvert_jusqua[cle3(r)] = max(ouvert_jusqua.get(cle3(r), 0), t_fin)

    if cp.FANTOMES:                                      # signaux fantômes
        exclus = {id(r) for r in top if r["decision"] == "TRADE NOW"}
        candidats = sorted([r for r in results if r["decision"] != "NO TRADE"
                            and r["score"] >= cp.SCORE_MIN and id(r) not in exclus], key=cle_prio)
        vus = set()
        for r in candidats:
            k = cle3(r)
            if k in vus or ouvert_jusqua.get(k, 0) > T \
                    or T - dernier_fantome.get(k, -1e18) <= cp.DEDUP_HEURES * H1:
                continue
            vus.add(k)
            statut = "EN_COURS" if (r["deja"] and r["dist"] <= cp.DIST_TRADE_NOW) else "ATTENTE"
            lg, t_fin = evaluer(cp.ligne_journal(r, maintenant, "FANTOME", statut))
            lignes.append(lg)
            dernier_fantome[k] = T
            ouvert_jusqua[k] = max(ouvert_jusqua.get(k, 0), t_fin)


def lancer(debut, fin):
    """Rejoue un scan à chaque clôture M15 entre debut et fin (fin = dernier instant
    permettant 96 h de suivi : 48 h pour déclencher + 48 h de trade)."""
    brancher()
    T0 = (debut // M15 + 1) * M15
    T_fin = ((fin - 2 * H48) // M15) * M15
    pas = list(range(T0, T_fin + 1, M15))
    etat, ouvert_jusqua, dernier_fantome, lignes = {}, {}, {}, []
    t0 = time.time()
    for i, T in enumerate(pas, 1):
        un_pas(T, etat, ouvert_jusqua, dernier_fantome, lignes)
        if i % 96 == 0 or i == len(pas):
            ecoule = time.time() - t0
            reste = ecoule / i * (len(pas) - i)
            n_reel = sum(1 for l in lignes if l["type"] == "REEL")
            print(f"  {cp.fmt_date(T)} — {i}/{len(pas)} pas — {n_reel} trades réels, "
                  f"{len(lignes) - n_reel} fantômes — reste ≈ {reste / 60:.0f} min", flush=True)
    return lignes, pas


# ---------------- RAPPORT ----------------
def au_marche(d):
    """Recalcule les trades réels comme si l'entrée se faisait au Market, au prix du signal.
    Mêmes SL / TP ; R et frais recalculés sur ce prix. Trades dont le RR au marché
    serait < RR_MIN : marqués « trop tard » (tu ne les aurais pas pris)."""
    d = d.copy()
    s = np.where(d["sens"] == "LONG", 1.0, -1.0)
    risque_m = s * (d["px_signal"] - d["sl"])
    risque_t = (d["entree"] - d["sl"]).abs()
    sortie = np.where(d["statut"] == "TP", d["tp"],
             np.where(d["statut"] == "SL", d["sl"], d["entree"] + s * d["resultat_R"] * risque_t))
    ok = risque_m > 0
    d["rr_marche"] = np.where(ok, s * (d["tp"] - d["px_signal"]) / risque_m.where(ok, 1), 0)
    d["resultat_R"] = np.where(ok, s * (sortie - d["px_signal"]) / risque_m.where(ok, 1), np.nan)
    d["frais_R"] = np.where(ok, 2 * cp.FRAIS_TAKER * d["px_signal"] / risque_m.where(ok, 1), np.nan)
    d["resultat_net_R"] = d["resultat_R"] - d["frais_R"]
    d["_rr_ok"] = np.where(d["rr_marche"] >= cp.RR_MIN, "RR au marché ≥ " + str(cp.RR_MIN),
                           "trop tard (RR au marché < " + str(cp.RR_MIN) + ")")
    return d[d["resultat_R"].notna()]


def rapport(lignes, pas, sauve, duree_calcul):
    j = pd.DataFrame(lignes, columns=cp.COLS_JOURNAL)
    for c in cp.COLS_TEXTE:
        j[c] = j[c].astype(object).where(j[c].notna(), "").astype(str)
    for c in cp.COLS_JOURNAL:
        if c not in cp.COLS_TEXTE:
            j[c] = pd.to_numeric(j[c], errors="coerce")
    j.to_csv("backtest_journal.csv", index=False)

    cp.STATS = "backtest_stats.md"
    cp.ecrire_stats(j)
    with open(cp.STATS, encoding="utf-8") as f:
        corps = f.read().split("\n", 1)[1]

    npaires = len(DATA) - (0 if "BTCUSDT" in DATA else 1)
    entete = [
        f"# 🔁 Backtest Crypto Pépite V{cp.VERSION} (logique V{getattr(cp, 'VERSION_LOGIQUE', cp.VERSION)})\n",
        f"_Période : du {cp.fmt_date(pas[0])} au {cp.fmt_date(pas[-1])} UTC "
        f"({len(pas) / 96:.0f} jours, {len(pas)} scans M15) — {npaires} paires — "
        f"source {sauve.get('source', '?')} — calcul {duree_calcul / 60:.0f} min._\n",
        "_Limites : OI absent de l'historique (composante OI du score fixée à 5) ; funding ignoré ; "
        f"spread supposé {SPREAD_SUPPOSE * 100:.2f} % ; paires = les plus liquides aujourd'hui (biais de survie) ; "
        "entrée au niveau théorique (en réel, l'écart constaté est d'environ +0,2 R)._\n"]

    reel = cp._prep(j[(j["type"] == "REEL") & j["statut"].isin(cp.STATUTS_CLOS)])
    fant = cp._prep(j[(j["type"] == "FANTOME") & j["statut"].isin(cp.STATUTS_CLOS)])
    marche = ["\n---\n\n## ⚠️ Résultat réaliste : entrée au Market (prix du signal)\n",
              "_Les tableaux ci-dessus comptent l'entrée au niveau de la zone, alors qu'au signal le prix "
              "est déjà au-dessus. Ici : mêmes trades, mêmes SL / TP, mais entrée au prix du signal "
              "(ce que tu obtiens en Market). C'est le chiffre à retenir._\n"]
    if len(reel):
        m = au_marche(reel)
        marche.append(cp._global(m))
        marche.append(cp._bloc_stats(m, "Selon le RR restant au prix du marché", "_rr_ok"))
        mm = m[m["rr_marche"] >= cp.RR_MIN]
        if len(mm):
            marche.append("\n**En ne gardant que les trades avec RR au marché ≥ " + str(cp.RR_MIN) + " :**\n")
            marche.append(cp._global(mm))
            marche.append(cp._bloc_tranches(mm, "Par distance à l'entrée (ATR H1)", "dist_ATR",
                                            [0, 0.15, 0.35, float("inf")], ["<0,15", "0,15-0,35", "≥0,35"]))
            marche.append(cp._bloc_stats(mm, "Par contexte BTC détaillé (H4-H1)", "btc_detail"))
            marche.append(cp._bloc_stats(mm, "Selon la tendance BTC H4", "btc_h4"))
            mm = mm.assign(semaine=pd.to_datetime(mm["date_utc"]).dt.strftime("%G-S%V"))
            marche.append(cp._bloc_stats(mm, "Par semaine", "semaine"))
    temps = ["\n---\n\n## Stabilité dans le temps et selon le marché\n"]
    if len(reel):
        reel["mois"] = reel["date_utc"].str[:7]
        reel["semaine"] = pd.to_datetime(reel["date_utc"]).dt.strftime("%G-S%V")
        temps.append(cp._bloc_stats(reel, "Trades réels par mois", "mois"))
        temps.append(cp._bloc_stats(reel, "Trades réels par semaine", "semaine"))
        temps.append(cp._bloc_stats(reel, "Trades réels selon la tendance BTC H4", "btc_h4"))
    if len(fant):
        fant["mois"] = fant["date_utc"].str[:7]
        for sens in ("LONG", "SHORT"):
            f = fant[fant["sens"] == sens]
            if len(f):
                temps.append(cp._bloc_stats(f, f"Fantômes {sens} par mois", "mois"))
        temps.append(cp._bloc_stats(fant, "Fantômes selon la tendance BTC H4 et le sens", "btc_h4"))

    with open(cp.STATS, "w", encoding="utf-8") as f:
        f.write("\n".join(entete) + corps + "\n".join(marche) + "\n".join(temps) + "\n")

    print("\n================ RÉSUMÉ ================")
    for nom, d in (("Trades réels (LONG)", reel), ("Fantômes", fant)):
        if len(d):
            w = (d["resultat_R"] > 0).mean() * 100
            print(f"{nom} : {len(d)} clôturés | réussite {w:.0f} % | "
                  f"{d['resultat_net_R'].mean():+.2f} R net/trade | total {d['resultat_net_R'].sum():+.1f} R")
    if len(reel):
        m = au_marche(reel)
        mm = m[m["rr_marche"] >= cp.RR_MIN]
        print(f"Trades réels AU MARCHÉ : {len(m)} | {m['resultat_net_R'].mean():+.2f} R net/trade | "
              f"total {m['resultat_net_R'].sum():+.1f} R  —  en ne gardant que RR ≥ {cp.RR_MIN} au marché : "
              f"{len(mm)} trades, {mm['resultat_net_R'].mean() if len(mm) else float('nan'):+.2f} R net/trade")
    print("Rapport complet : backtest_stats.md — détail : backtest_journal.csv")


def main():
    ap = argparse.ArgumentParser(description="Backtest Crypto Pépite")
    ap.add_argument("--jours", type=int, default=60, help="durée de l'historique rejoué")
    ap.add_argument("--paires", type=int, default=60, help="nb de paires (les plus liquides)")
    ap.add_argument("--retelecharger", action="store_true", help="ignorer les données déjà téléchargées")
    a = ap.parse_args()
    global DATA, INFO
    print(f"BACKTEST CRYPTO PÉPITE V{cp.VERSION} — {a.jours} jours, {a.paires} paires")
    sauve = charger_donnees(a.jours, a.paires, a.retelecharger)
    DATA, INFO = sauve["data"], sauve["info"]
    if "BTCUSDT" not in DATA:
        sys.exit("⛔ Historique BTC indisponible : impossible de calculer le contexte BTC.")
    print(f"{len(DATA)} paires chargées. Rejeu des scans…")
    t0 = time.time()
    lignes, pas = lancer(sauve["debut"], sauve["fin"])
    rapport(lignes, pas, sauve, time.time() - t0)


if __name__ == "__main__":
    main()
