# ==============================================================================
#  BACKTEST CRYPTO PÉPITE v3 — rejoue crypto_pepite.py (la version présente dans
#  le même dossier : V6.5 et suivantes) sur l'historique
#
#  Principe : le script importe TON scanner et appelle ses propres fonctions
#  (analyse avec TOUS ses filtres, zones, bougie de rejet, score, filtre BTC, suivi
#  TP/SL, simulation des sorties, statistiques). Seules les bougies sont remplacées :
#  à chaque pas de 15 min, le scanner ne voit que les bougies DÉJÀ CLÔTURÉES.
#
#  Utilisation (Colab ou PC, crypto_pepite.py dans le même dossier) :
#     python backtest_pepite.py --jours 30 --paires 40                  # comme avant
#     python backtest_pepite.py --jours 30 --paires 40 --entree marche  # entrée au marché
#     python backtest_pepite.py --jours 30 --paires 40 --entree limite  # ordre limite
#     ajouter --une-position : une seule position à la fois par paire
#
#  NOUVEAU v2 :
#   - --entree theorique (défaut, comme la v1) : rempli pile au niveau d'entrée.
#   - --entree marche : rempli au prix du signal (clôture M15), SL et TP inchangés,
#     R et frais recalculés sur la vraie distance entrée–SL.
#   - --entree limite : ordre posé au niveau d'entrée, rempli SEULEMENT si le prix
#     y revient dans les --limite-h heures (défaut 2 h). Sinon : « RATE » (parti au TP
#     sans revenir = gagnant manqué), « INVALIDE » (parti au SL = perte évitée)
#     ou « NON_DECLENCHE » (resté entre les deux). Taux de remplissage en tête du rapport.
#   - --une-position : pas de nouveau trade réel sur une paire tant que le précédent
#     n'est pas clôturé (comme un trader réel).
#
#  NOUVEAU v8 : 4e scanner « Trio Alt » (--scanner trio_alt) : trois setups dans un seul
#   fichier, détaillés séparément (par mois et setup, selon BTC H4 et le setup).
#
#  NOUVEAU v7 : si le scanner tient des compteurs DIAG (Excès Alt), le rapport et le résumé
#   indiquent combien de candidats passent chaque étape (pour voir où ça bloque).
#
#  NOUVEAU v6 : 3e scanner « Excès Alt » (--scanner exces_alt) et détail adapté
#   (écart de performance avec BTC par tranches au-delà du seuil d'excès).
#
#  NOUVEAU v5 (2e scanner « Tendance Alt » et test en deux temps) :
#   - --scanner tendance_alt : teste tendance_alt.py au lieu de crypto_pepite.py
#     (les deux fichiers doivent être dans le même dossier).
#   - --de AAAA-MM-JJ / --a AAAA-MM-JJ : ne rejoue que cette période (les données
#     téléchargées restent les mêmes). Ex. mise au point --de 2026-06-01 --a 2026-07-31,
#     puis validation --de 2026-08-01 --a 2026-09-30.
#   - Un scanner peut fournir preparer_scan() et prefiltre() : le backtest les utilise.
#
#  NOUVEAU v4 (pour le scanner V7.x : « ce que je reçois sur Telegram ») :
#   - Section « Alertes Telegram V7 » : résultat des alertes selon chaque indication de la
#     fiche (⭐ BTC en range H4, zone ✅/⚠️, bougie ✅/⚠️, frais ✅/⚠️) et selon le nombre de ✅.
#     But : savoir quelles indications de la fiche méritent ton attention.
#
#  NOUVEAU v3 :
#   - --regle NOM=VALEUR : change un réglage du scanner pour ce backtest seulement,
#     sans toucher au fichier (répétable). Exemples :
#       --regle FILTRE_BTC_H4_RANGE=True     (tester le filtre « BTC en range en H4 »)
#       --regle FILTRE_BOUGIE=False          (tester sans le filtre de bougie)
#     Les réglages modifiés sont écrits en tête du rapport.
#   - Tableau « par mois » détaillé aussi par tendance BTC H4, pour voir si une règle
#     tient mois après mois (pas seulement en moyenne).
#
#  Résultats : backtest_stats.md (même présentation que ton journal)
#              backtest_journal.csv (tous les signaux, une ligne par signal)
#
#  Limites (écrites aussi en tête du rapport) :
#   - OI : pas d'historique -> composante OI du score fixée à 5 (comme « OI n/d »)
#   - funding non pris en compte, spread supposé à 0,05 %
#   - paires = les plus liquides AUJOURD'HUI (biais de survie)
# ==============================================================================
import argparse, importlib, math, os, pickle, sys, time
from types import SimpleNamespace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests


def _nom_scanner():
    """Le scanner à tester est lu avant tout le reste (option --scanner, défaut crypto_pepite)."""
    for i, a in enumerate(sys.argv):
        if a == "--scanner" and i + 1 < len(sys.argv):
            return sys.argv[i + 1].removesuffix(".py")
        if a.startswith("--scanner="):
            return a.split("=", 1)[1].removesuffix(".py")
    return "crypto_pepite"


SCANNER = _nom_scanner()
cp = importlib.import_module(SCANNER)
NOM = getattr(cp, "NOM_SCANNER", "Crypto Pépite")

BACKTEST_VERSION = "8"
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

# Options (remplies par main)
MODE_ENTREE = "theorique"
LIMITE_MS = 2 * H1
UNE_POSITION = False
POSITIONS = {}          # paire -> instant de clôture du dernier trade réel
REGLES = []             # réglages du scanner modifiés pour ce backtest (texte, pour le rapport)


def appliquer_regle(texte):
    """--regle NOM=VALEUR : modifie un réglage de crypto_pepite.py pour ce backtest."""
    if "=" not in texte:
        sys.exit(f"⛔ --regle {texte} : format attendu NOM=VALEUR (ex. FILTRE_BTC_H4_RANGE=True)")
    nom, val = (x.strip() for x in texte.split("=", 1))
    if not hasattr(cp, nom):
        sys.exit(f"⛔ --regle : le réglage « {nom} » n'existe pas dans crypto_pepite.py")
    actuel = getattr(cp, nom)
    if isinstance(actuel, bool):
        if val.lower() not in ("true", "false", "1", "0", "oui", "non"):
            sys.exit(f"⛔ --regle {nom} : valeur attendue True ou False")
        v = val.lower() in ("true", "1", "oui")
    elif isinstance(actuel, int):
        v = int(val)
    elif isinstance(actuel, float):
        v = float(val)
    else:
        v = val
    setattr(cp, nom, v)
    REGLES.append(f"{nom} = {v!r} (au lieu de {actuel!r})")


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


def evaluer(lg, fenetre_attente=H48):
    """Renvoie (ligne mise à jour, instant où le signal cesse d'être « ouvert »).
    fenetre_attente : durée pendant laquelle un signal en ATTENTE peut être déclenché
    (48 h pour les fantômes, durée de validité de l'ordre en mode limite)."""
    sym, ts = lg["symbol"], lg["ts"]
    if lg["statut"] == "EN_COURS":
        t_e = ts
    else:
        if not couvert(sym, ts + fenetre_attente):
            return lg, math.inf
        p = cp.parcours(lg, tranche(sym, ts, ts + fenetre_attente), False)
        if p["statut"] in ("INVALIDE", "RATE"):
            lg.update(statut=p["statut"], date_sortie=cp.fmt_date(p["t_sortie"] or ts))
            return lg, p["t_sortie"] or ts
        if not p["actif"]:
            lg.update(statut="NON_DECLENCHE", date_sortie=cp.fmt_date(ts + fenetre_attente))
            return lg, ts + fenetre_attente
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


def entree_marche(lg, r):
    """v2 : trade rempli au prix du signal. SL et TP inchangés ; R, RR et frais recalculés.
    Renvoie False si le prix du signal est déjà au-delà du TP ou du SL (trade impossible)."""
    t = r["inf"].get("tick")
    e = cp.arrondi(r["px"], t)
    d = 1 if lg["sens"] == "LONG" else -1
    risque = d * (e - lg["sl"])
    gain = d * (lg["tp"] - e)
    if risque <= 0 or gain <= 0:
        return False
    lg.update(entree=e, rr=round(gain / risque, 2), ecart_entree_R=0.0,
              frais_R=round(2 * cp.FRAIS_TAKER * e / risque, 2))
    return True


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
    if hasattr(cp, "preparer_scan"):                    # ex. force relative de Tendance Alt
        cp.preparer_scan([sym for _, sym, _, _ in liq[:cp.SHORTLIST]])
    filtre = cp.prefiltre if hasattr(cp, "prefiltre") else prix_dans_une_zone
    for tv, sym, ch24, px in liq[:cp.SHORTLIST]:
        if not filtre(sym):
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
        if UNE_POSITION and POSITIONS.get(r["symbol"], 0) > T:
            continue                                     # position déjà ouverte sur cette paire
        lg = cp.ligne_journal(r, maintenant, "REEL", "EN_COURS")
        fenetre = H48
        if MODE_ENTREE == "marche":
            if not entree_marche(lg, r):
                lg.update(statut="INVALIDE", date_sortie=cp.fmt_date(T), ts_entree=np.nan)
                lignes.append(lg)
                etat[cp.cle_signal(r)] = maintenant
                continue
        elif MODE_ENTREE == "limite":
            lg.update(statut="ATTENTE", ts_entree=np.nan, mfe_R=np.nan, mae_R=np.nan)
            fenetre = LIMITE_MS
        lg, t_fin = evaluer(lg, fenetre)
        lignes.append(lg)
        etat[cp.cle_signal(r)] = maintenant
        ouvert_jusqua[cle3(r)] = max(ouvert_jusqua.get(cle3(r), 0), t_fin)
        POSITIONS[r["symbol"]] = max(POSITIONS.get(r["symbol"], 0), t_fin)

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


PERIODE = [None, None]      # --de / --a, en ms


def lancer(debut, fin):
    """Rejoue un scan à chaque clôture M15 entre debut et fin (fin = dernier instant
    permettant 96 h de suivi : 48 h pour déclencher + 48 h de trade)."""
    brancher()
    POSITIONS.clear()
    T0 = (debut // M15 + 1) * M15
    T_fin = ((fin - 2 * H48) // M15) * M15
    pas = list(range(T0, T_fin + 1, M15))
    if PERIODE[0]: pas = [T for T in pas if T >= PERIODE[0]]
    if PERIODE[1]: pas = [T for T in pas if T < PERIODE[1]]
    if not pas:
        sys.exit("⛔ Aucun scan dans la période demandée (vérifie --de / --a et --jours).")
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
def texte_entree():
    if MODE_ENTREE == "marche":
        return "entrée AU MARCHÉ au prix du signal (R et frais recalculés sur la vraie distance entrée–SL)"
    if MODE_ENTREE == "limite":
        return (f"entrée en ORDRE LIMITE au niveau d'entrée, valable {LIMITE_MS / H1:g} h "
                "(rempli seulement si le prix revient le toucher)")
    return "entrée au niveau THÉORIQUE (en réel, l'écart constaté est d'environ +0,2 R)"


def bloc_fiche(reel):
    """v4 : résultats des alertes selon les indications ✅ / ⚠️ de la fiche Telegram V7."""
    if hasattr(cp, "preparer_scan"):                 # Tendance Alt, Excès Alt
        d = reel.copy()
        d["mois_sens"] = d["mois"] + " · " + d["sens"]
        if NOM == "Excès Alt":
            bornes, noms = [0, 30, 50, 1e9], ["< 30 %", "30-50 %", "≥ 50 %"]
        else:
            bornes, noms = [0, 5, 10, 20, 1e9], ["< 5 %", "5-10 %", "10-20 %", "≥ 20 %"]
        d["f_force"] = pd.cut(d["force_vs_btc"].abs() * 100, bornes, labels=noms, right=False)
        d["btc_h4_sens"] = d["btc_h4"] + " · " + d["sens"]
        blocs = [f"\n---\n\n## {NOM} — détail\n"]
        if d["setup"].nunique() > 1:                 # v8 : plusieurs setups dans un même scanner
            d["mois_setup"] = d["mois"] + " · " + d["setup"]
            d["btc_h4_setup"] = d["setup"] + " · BTC H4 " + d["btc_h4"]
            blocs += [cp._bloc_stats(d, "Par mois et setup", "mois_setup"),
                      cp._bloc_stats(d, "Selon le setup et BTC H4", "btc_h4_setup")]
        return blocs + [
                cp._bloc_stats(d, "Par mois et sens", "mois_sens"),
                cp._bloc_stats(d, "Selon l'écart de performance avec BTC (3 jours)", "f_force", noms),
                cp._bloc_stats(d, "Selon BTC H4 et le sens", "btc_h4_sens")]
    if not hasattr(cp, "FRAIS_ALERTE_R"):
        return []                                     # scanner antérieur à la V7 : section sans objet
    d = reel.copy()
    ok = lambda b: b.map({True: "✅", False: "⚠️"})
    d["f_btc"] = (d["btc_h4"] == cp.NEUTRE).map({True: "⭐ BTC en range H4", False: "BTC en tendance H4"})
    zone = (d["touches_zone"] >= cp.ZONE_TESTS_MIN) | (d["age_zone_h"] >= cp.ZONE_AGE_MIN_H)
    bougie = (d["close_pos"] >= cp.CLOSE_POS_FORT) | (d["body_ratio"] >= cp.BODY_FORT)
    frais = d["frais_R"] <= cp.FRAIS_ALERTE_R
    d["f_zone"], d["f_bougie"], d["f_frais"] = ok(zone), ok(bougie), ok(frais)
    d["f_nb"] = ((d["btc_h4"] == cp.NEUTRE).astype(int) + zone.astype(int) + bougie.astype(int)
                 + frais.astype(int)).astype(str) + " sur 4"
    return ["\n---\n\n## Alertes Telegram V7 — que valent les indications de la fiche ?\n",
            "_Chaque alerte reçue est classée selon ce que la fiche affichait. "
            "Ce sont des constats sur le passé, pas des règles : un écart ne compte que s'il est "
            "net, sur beaucoup de trades, et stable d'un mois à l'autre._",
            cp._bloc_stats(d, "Selon BTC (⭐)", "f_btc"),
            cp._bloc_stats(d, "Selon la zone H1", "f_zone"),
            cp._bloc_stats(d, "Selon la bougie M15", "f_bougie"),
            cp._bloc_stats(d, "Selon les frais", "f_frais"),
            cp._bloc_stats(d, "Selon le nombre de bons signes (⭐ + ✅)", "f_nb"),
            cp._bloc_stats(d.assign(m=d["mois"] + " · " + d["f_nb"]), "Par mois et nombre de bons signes", "m")]


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
        f"# 🔁 Backtest {NOM} V{cp.VERSION} (backtest v{BACKTEST_VERSION})\n",
        f"_Période : du {cp.fmt_date(pas[0])} au {cp.fmt_date(pas[-1])} UTC "
        f"({len(pas) / 96:.0f} jours, {len(pas)} scans M15) — {npaires} paires — "
        f"source {sauve.get('source', '?')} — calcul {duree_calcul / 60:.0f} min._\n",
        f"_Mode d'entrée : **{texte_entree()}**"
        + (" — **une seule position à la fois par paire**" if UNE_POSITION else "") + "._\n",
        ("_Réglages modifiés pour ce backtest : **" + " ; ".join(REGLES) + "**._\n") if REGLES
        else "_Réglages du scanner : ceux du fichier, sans modification._\n",
        "_Limites : OI absent de l'historique (composante OI du score fixée à 5) ; funding ignoré ; "
        f"spread supposé {SPREAD_SUPPOSE * 100:.2f} % ; paires = les plus liquides aujourd'hui (biais de survie)._\n"]

    if hasattr(cp, "DIAG"):
        etapes = " → ".join(f"{k[2:].replace('_', ' ')} {v}" for k, v in cp.DIAG.items())
        entete.append(f"_Entonnoir (scans × paires) : {etapes}._\n")
    reels_tous = j[j["type"] == "REEL"]
    if len(reels_tous):
        jours = max(1, len(pas) / 96)
        n_clos = int(reels_tous["statut"].isin(cp.STATUTS_CLOS).sum())
        entete.append(f"_Fréquence : {len(reels_tous)} signaux TRADE NOW, {n_clos} trades pris, "
                      f"soit ≈ {n_clos / jours:.1f} trades par jour._\n")
        if MODE_ENTREE in ("limite", "marche"):
            cpt = reels_tous["statut"].value_counts()
            rate, inval, nd = cpt.get("RATE", 0), cpt.get("INVALIDE", 0), cpt.get("NON_DECLENCHE", 0)
            if MODE_ENTREE == "limite":
                entete.append(
                    f"_Ordres limite : **{n_clos}/{len(reels_tous)} remplis "
                    f"({100 * n_clos / len(reels_tous):.0f} %)** — non remplis : {rate} partis au TP sans revenir "
                    f"(gagnants manqués), {inval} partis au SL avant (pertes évitées), "
                    f"{nd} restés sans toucher l'entrée._\n")
            elif inval:
                entete.append(f"_Entrée au marché impossible (prix déjà au-delà du TP ou du SL) : {inval} signaux._\n")

    reel = cp._prep(j[(j["type"] == "REEL") & j["statut"].isin(cp.STATUTS_CLOS)])
    fant = cp._prep(j[(j["type"] == "FANTOME") & j["statut"].isin(cp.STATUTS_CLOS)])
    temps = ["\n---\n\n## Stabilité dans le temps et selon le marché\n"]
    if len(reel):
        reel["mois"] = reel["date_utc"].str[:7]
        reel["semaine"] = pd.to_datetime(reel["date_utc"]).dt.strftime("%G-S%V")
        temps.append(cp._bloc_stats(reel, "Trades réels par mois", "mois"))
        temps.append(cp._bloc_stats(reel, "Trades réels par semaine", "semaine"))
        temps.append(cp._bloc_stats(reel, "Trades réels selon la tendance BTC H4", "btc_h4"))
        reel["mois_btc_h4"] = reel["mois"] + " · BTC H4 " + reel["btc_h4"]
        temps.append(cp._bloc_stats(reel, "Trades réels par mois et tendance BTC H4", "mois_btc_h4"))
        temps += bloc_fiche(reel)
    if len(fant):
        fant["mois"] = fant["date_utc"].str[:7]
        for sens in ("LONG", "SHORT"):
            f = fant[fant["sens"] == sens]
            if len(f):
                temps.append(cp._bloc_stats(f, f"Fantômes {sens} par mois", "mois"))
        temps.append(cp._bloc_stats(fant, "Fantômes selon la tendance BTC H4 et le sens", "btc_h4"))
        temps.append(cp._bloc_stats(fant, "Fantômes par raison de non-trade (dont filtres V6.4 / V6.5)", "raison"))

    with open(cp.STATS, "w", encoding="utf-8") as f:
        f.write("\n".join(entete) + corps + "\n".join(temps) + "\n")

    print("\n================ RÉSUMÉ ================")
    print(f"Scanner V{cp.VERSION} — {texte_entree()}" + (" — une position par paire" if UNE_POSITION else ""))
    for nom, d in (("Trades réels", reel), ("Fantômes", fant)):
        if len(d):
            w = (d["resultat_R"] > 0).mean() * 100
            print(f"{nom} : {len(d)} clôturés | réussite {w:.0f} % | "
                  f"{d['resultat_net_R'].mean():+.2f} R net/trade | total {d['resultat_net_R'].sum():+.1f} R")
    if hasattr(cp, "DIAG"):
        print("Entonnoir : " + " → ".join(f"{k[2:].replace('_', ' ')} {v}" for k, v in cp.DIAG.items()))
    print("Rapport complet : backtest_stats.md — détail : backtest_journal.csv")


def main():
    global DATA, INFO, MODE_ENTREE, LIMITE_MS, UNE_POSITION
    ap = argparse.ArgumentParser(description="Backtest Crypto Pépite")
    ap.add_argument("--jours", type=int, default=60, help="durée de l'historique rejoué")
    ap.add_argument("--paires", type=int, default=60, help="nb de paires (les plus liquides)")
    ap.add_argument("--retelecharger", action="store_true", help="ignorer les données déjà téléchargées")
    ap.add_argument("--entree", choices=["theorique", "marche", "limite"], default="theorique",
                    help="façon d'entrer en position (défaut : theorique)")
    ap.add_argument("--limite-h", type=float, default=2.0,
                    help="durée de validité de l'ordre limite, en heures (défaut 2)")
    ap.add_argument("--une-position", action="store_true",
                    help="une seule position à la fois par paire")
    ap.add_argument("--scanner", default="crypto_pepite", help="crypto_pepite (défaut), tendance_alt, exces_alt ou trio_alt")
    ap.add_argument("--de", help="début de la période rejouée, AAAA-MM-JJ")
    ap.add_argument("--a", dest="a_", help="fin de la période rejouée (jour inclus), AAAA-MM-JJ")
    ap.add_argument("--regle", action="append", default=[],
                    help="réglage du scanner à modifier, NOM=VALEUR (répétable)")
    a = ap.parse_args()
    MODE_ENTREE, LIMITE_MS, UNE_POSITION = a.entree, int(a.limite_h * H1), a.une_position
    jour_ms = lambda x: int(datetime.strptime(x, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    PERIODE[0] = jour_ms(a.de) if a.de else None
    PERIODE[1] = jour_ms(a.a_) + JOUR if a.a_ else None
    for r in a.regle:
        appliquer_regle(r)
    print(f"BACKTEST {NOM.upper()} V{cp.VERSION} (backtest v{BACKTEST_VERSION}) — {a.jours} jours, "
          f"{a.paires} paires — entrée {MODE_ENTREE}" + (" — une position par paire" if UNE_POSITION else "")
          + (" — réglages : " + " ; ".join(REGLES) if REGLES else ""))
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
