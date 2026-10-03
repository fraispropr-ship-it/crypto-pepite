# ==============================================================================
#  TRIO ALT V1.0 — 4e scanner, INDÉPENDANT des autres (Zoomex Futures USDT)
#  Trois setups « classiques », LONG uniquement, étiquetés séparément dans le journal
#  pour savoir setup par setup ce qui tient (colonne « setup », tableau « Par setup »).
#
#  Règles communes :
#    - Paires liquides (volume 24 h >= 5 M USDT, spread <= 0,15 %), mouvement 24 h <= 15 %.
#    - Jamais contre la tendance H4 de l'altcoin. Pas de trade pendant un choc BTC baissier.
#    - Déclencheur : bougie M15 clôturée qui REJETTE la zone (mèche dans la zone, clôture
#      au-dessus, bougie verte) ET franche (clôture >= 80 % de la bougie OU corps >= 60 %).
#      Bougie pas assez franche -> WAIT, suivi en FANTÔME (pour vérifier que le filtre a raison).
#    - Entrée : clôture de la bougie M15. Frais aller-retour <= FRAIS_MAX_R, sinon WAIT.
#    - Risque 1 USDT, TP plafonné à 2 R.
#
#  SETUP 1 — « Pullback tendance H4 »
#    1. Altcoin en tendance haussière H4 (prix > moyenne 50, moyenne 20 > 50 et montante).
#    2. Le prix était nettement au-dessus (>= PULL_HAUT ATR H1 au-dessus de la moyenne 20 H4
#       dans les 24 dernières heures), puis revient dans la zone de la moyenne 20 H4
#       (± PULL_TOL ATR H1).
#    3. Rejet M15 de cette zone. SL sous le creux du repli (- SL_MARGE ATR H1). TP fixe 2 R.
#    4. BTC baissier en H4 -> WAIT (fantôme).
#
#  SETUP 2 — « Cassure + retest H1 »
#    1. Une bougie H1 des RETEST_BARRES dernières heures a clôturé au-dessus d'une résistance
#       H1 testée au moins ZONE_TESTS_MIN fois (calculée AVANT la cassure), alors qu'aucune
#       des CASSURE_RECUL clôtures H1 précédentes n'était au-dessus, avec un volume
#       >= CASSURE_VOL x la moyenne des 20 bougies précédentes.
#    2. Depuis, aucune clôture H1 n'est repassée sous le bas de la zone (la cassure tient).
#    3. Le prix revient tester la zone : rejet M15 (le retest est VÉRIFIÉ, contrairement aux
#       cassures de Crypto Pépite avant la V6). SL sous la zone. TP fixe 2 R.
#    4. BTC baissier en H4 -> WAIT (fantôme).
#
#  SETUP 3 — « Rebond bas de range »
#    1. Altcoin sans tendance en H4. Range H1 : un support testé >= ZONE_TESTS_MIN fois et
#       une résistance testée >= RANGE_RES_TESTS fois, écartés d'au moins RANGE_MIN_ATR ATR H1.
#    2. Rejet M15 du support, clôture dans le quart bas du range (RANGE_BAS).
#    3. SL sous le support. TP au MILIEU du range, plafonné à 2 R ; écarté si < RR_MIN.
#    4. BTC pas en range en H4 (ou indisponible) -> WAIT (fantôme).
#
#  Compteurs DIAG : combien de fois chaque étape est franchie (scans x paires), affichés
#  par le backtest pour voir où ça bloque.
#  Fichiers propres : journal_trio_alt.csv, journal_trio_alt_stats.md, etat_trio_alt.json.
#  Alertes Telegram marquées « 🎯 TRIO ALT ».
#  V1.0 : version de test — mise au point sur juin-juillet, validation unique sur
#         août-septembre AVANT toute mise en ligne (aucune alerte tant que ce n'est pas validé).
#  Ne lit pas les réponses « pris » / « non » (réservé à Crypto Pépite pour l'instant).
#  NE couvre PAS : news / macro -> à vérifier toi-même avant d'entrer.
# ==============================================================================
import os, re, json, time, math, requests
import numpy as np, pandas as pd
from datetime import datetime, timezone
from decimal import Decimal
from html import escape, unescape

NOM_SCANNER     = "Trio Alt"
VERSION         = "1.0"   # numéro du script : change à CHAQUE modification
VERSION_LOGIQUE = "1.0"   # regroupe les stats : ne change que si les signaux changent

# ---------------- RÉGLAGES DES SETUPS ----------------
SETUP_PULLBACK = True    # setup 1 actif
SETUP_CASSURE  = True    # setup 2 actif
SETUP_RANGE    = True    # setup 3 actif
SL_MARGE       = 0.3     # marge sous le creux / la zone, en ATR H1
FRAIS_MAX_R    = 0.15    # frais aller-retour max, en R (au-delà : WAIT)
TP_R           = 2.0     # objectif plafonné à 2 R
FORCE_H        = 72      # performance comparée à BTC (information seulement), en heures
# Setup 1 — pullback
PULL_TOL       = 0.3     # demi-largeur de la zone autour de la moyenne 20 H4, en ATR H1
PULL_HAUT      = 1.5     # le prix doit être monté d'au moins PULL_HAUT ATR H1 au-dessus de la moyenne
PULL_HAUT_H    = 24      # ... dans les PULL_HAUT_H dernières heures
PULL_CREUX_M15 = 12      # creux du repli : plus bas des 12 dernières M15 (3 h)
# Setup 2 — cassure + retest
RETEST_BARRES  = 12      # le retest doit arriver dans les 12 bougies H1 qui suivent la cassure
CASSURE_RECUL  = 24      # aucune des 24 clôtures H1 précédentes au-dessus de la résistance
CASSURE_VOL    = 1.5     # volume de la bougie de cassure / moyenne des 20 précédentes
CASSURE_TEST_H = 48      # dernier test de la résistance au plus 48 h avant la cassure
# Setup 3 — range
RANGE_MIN_ATR  = 3.0     # hauteur mini du range, en ATR H1
RANGE_BAS      = 0.25    # la bougie doit clôturer dans le quart bas du range
RANGE_RES_TESTS = 2      # nb de tests mini de la résistance
# Filtres communs
ZONE_TESTS_MIN = 3       # nb de tests mini d'une zone H1 (résistance cassée, support du range)
FILTRE_BOUGIE  = True    # bougie de rejet franche exigée (sinon WAIT, suivi en fantôme)
CLOSE_POS_FORT = 0.8     # clôture M15 dans les 20 % hauts de la bougie
BODY_FORT      = 0.6     # ou corps >= 60 % de la bougie
BTC_BAISSIER_BLOQUE = True   # setups 1 et 2 : BTC baissier en H4 -> WAIT
RANGE_BTC_RANGE     = True   # setup 3 : seulement si BTC est en range en H4, sinon WAIT

# ---------------- PARAMÈTRES GÉNÉRAUX ----------------
BASE          = "https://openapi.zoomex.com"
CAPITAL       = 100.0
RISQUE        = 1.0
FRAIS_TAKER   = 0.0006
MIN_TURNOVER  = 5_000_000
MAX_SPREAD    = 0.0015
MAX_MOVE_24H  = 0.15          # anti-FOMO : > 15 % sur 24 h = mouvement passé
SHORTLIST     = 120
MARGE_CIBLE   = 20.0
RR_MIN        = 1.5
SCORE_MIN     = 0
MAX_TOP       = 50
MAX_TRADE_NOW = 50
DIST_TRADE_NOW = 0.35

BTC_FILTRE      = True
BTC_MALUS_FORT  = 15
BTC_MALUS_MOYEN = 7
BTC_BONUS       = 0
BTC_CHOC        = 0.012
CORR_FORTE      = 0.6
CORR_FAIBLE     = 0.3
CORR_WAIT       = 0.5
BTC_NEUTRE_1UT        = 4
BTC_NEUTRE_2UT        = 8
BTC_NEUTRE_CASSURE    = 3
SCORE_MIN_BTC_NEUTRE  = 0
MAX_NOW_BTC_NEUTRE    = 50

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ETAT_FICHIER     = "etat_trio_alt.json"
DEDUP_HEURES     = 6
LIRE_DECISIONS   = False

TV_PREFIXE = "ZOOMEX:"
TV_SUFFIXE = ".P"
PREPARE_ALERTE    = False
PREPARE_SCORE_MIN = 90

JOURNAL          = "journal_trio_alt.csv"
STATS            = "journal_trio_alt_stats.md"
SCAN_CSV         = "scan_trio_alt.csv"
JOURNAL_EXPIRE_H = 48

CASSURES_ACTIVES  = False
BTC_JAMAIS_CONTRE = False
TRI_PAR_SCORE     = False
FANTOMES          = True
KLINES_JOURNAL    = 500
BACKFILL_MAX      = 15
BTC_WAIT_TENDANCE = False
BTC_IMPACT_SCORE  = False
SHORT_MODE        = "FANTOME" # Trio Alt ne produit que des LONG
CLOSE_POS_MIN     = 0.6
REJET_VOLUME_OBLIGATOIRE = False
REJET_VOLUME_MIN  = 1.0
ZONE_LARGEUR_MAX  = 1.0
TRAIL_N           = 3
SIM_MAX           = 25
ZONE_TESTS_MIN, ZONE_AGE_MIN_H, CLOSE_POS_FORT, BODY_FORT = 3, 72, 0.8, 0.6
PRIO = {"TRADE NOW": 0, "PREPARE": 1, "WAIT": 2, "NO TRADE": 3}
NEUTRE = "NEUTRE/RANGE"

S = requests.Session()
OI_STATS = {"ok": 0, "ko": 0}
OI_SOURCE = None
BTC_CTX   = None

def get(path, **params):
    for _ in range(3):
        try:
            r = S.get(BASE + path, params=params, timeout=15)
            if r.status_code in (403, 451):
                raise SystemExit(f"⛔ HTTP {r.status_code} : Zoomex refuse cette connexion "
                                 "(IP géobloquée ?). Lance le script depuis ton PC.")
            j = r.json()
            if j.get("retCode") == 0:
                return j["result"]
        except SystemExit:
            raise
        except Exception:
            pass
        time.sleep(0.5)
    return None

# ---------------- DONNÉES ----------------
def tickers():
    res = get("/cloud/trade/v3/market/tickers", category="linear")
    if not res:
        raise SystemExit("Impossible de lire les tickers Zoomex.")
    df = pd.DataFrame(res["list"])
    for c in ["lastPrice", "price24hPcnt", "turnover24h", "fundingRate", "bid1Price", "ask1Price"]:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
    df = df[df.symbol.str.endswith("USDT")].copy()
    df["spread"] = (df.ask1Price - df.bid1Price) / df.lastPrice
    return df

def instruments():
    res = get("/cloud/trade/v3/market/instruments-info", category="linear", limit=1000)
    info = {}
    for it in (res or {}).get("list", []):
        try:
            info[it["symbol"]] = dict(tick=float(it["priceFilter"]["tickSize"]),
                                      step=float(it["lotSizeFilter"]["qtyStep"]),
                                      minq=float(it["lotSizeFilter"]["minOrderQty"]))
        except Exception:
            pass
    return info

def _klines_df(res):
    if not res or not res.get("list"):
        return None
    df = pd.DataFrame(res["list"]).iloc[:, :6]
    df.columns = ["t", "o", "h", "l", "c", "v"]
    return df.astype(float).sort_values("t").reset_index(drop=True)

def klines(sym, interval, limit=200):
    df = _klines_df(get("/cloud/trade/v3/market/kline", category="linear",
                        symbol=sym, interval=interval, limit=limit))
    if df is None:
        return None
    return df.iloc[:-1].reset_index(drop=True)   # bougies CLÔTURÉES uniquement

def klines_periode(sym, debut_ms, fin_ms):
    """V6 : bougies M15 d'une période passée (rattrapage du MFE des anciens trades)."""
    df = _klines_df(get("/cloud/trade/v3/market/kline", category="linear", symbol=sym,
                        interval="15", start=int(debut_ms), end=int(fin_ms), limit=1000))
    if df is None or df.t.iloc[0] > debut_ms + 900_000:
        return None                                  # période non couverte
    return df

# ---------------- OPEN INTEREST (multi-sources) ----------------
def _oi_binance(sym):
    r = S.get("https://fapi.binance.com/futures/data/openInterestHist",
              params=dict(symbol=sym, period="1h", limit=25), timeout=15)
    if r.status_code != 200: return None
    d = r.json()
    if not isinstance(d, list): return None
    return [(int(x["timestamp"]), float(x["sumOpenInterest"])) for x in d]

def _oi_okx(sym):
    inst = sym[:-4] + "-USDT-SWAP"
    r = S.get("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",
              params=dict(instId=inst, period="1H", limit=25), timeout=15)
    if r.status_code != 200: return None
    j = r.json()
    if j.get("code") != "0": return None
    return [(int(x[0]), float(x[1])) for x in j.get("data", [])]

def _oi_gate(sym):
    c = sym[:-4] + "_USDT"
    r = S.get("https://api.gateio.ws/api/v4/futures/usdt/contract_stats",
              params=dict(contract=c, interval="1h", limit=25), timeout=15)
    if r.status_code != 200: return None
    d = r.json()
    if not isinstance(d, list): return None
    return [(int(x["time"]) * 1000, float(x["open_interest"])) for x in d]

def _oi_bybit(sym):
    r = S.get("https://api.bybit.com/v5/market/open-interest",
              params=dict(category="linear", symbol=sym, intervalTime="1h", limit=25), timeout=15)
    if r.status_code != 200: return None
    j = r.json()
    if j.get("retCode") != 0: return None
    return [(int(x["timestamp"]), float(x["openInterest"])) for x in j["result"]["list"]]

SOURCES_OI = [("Binance", _oi_binance), ("OKX", _oi_okx), ("Gate", _oi_gate), ("Bybit", _oi_bybit)]

def choisir_source_oi():
    global OI_SOURCE
    for nom, f in SOURCES_OI:
        try:
            pts = f("BTCUSDT")
            if pts and len(pts) >= 25:
                OI_SOURCE = (nom, f)
                print(f"OI : source {nom} OK")
                return
            print(f"  OI : {nom} indisponible depuis ta connexion")
        except Exception as ex:
            print(f"  OI : {nom} injoignable ({type(ex).__name__})")
    print("⚠️ OI : aucune source accessible — l'OI sera en n/d")

def oi_change(sym):
    if OI_SOURCE is None:
        OI_STATS["ko"] += 1
        return None, None
    for _ in range(2):
        try:
            pts = OI_SOURCE[1](sym)
        except Exception:
            time.sleep(0.5); continue
        if not pts or len(pts) < 25:
            break
        pts.sort(key=lambda x: x[0], reverse=True)
        oi = [v for _, v in pts]
        if oi[4] <= 0 or oi[24] <= 0:
            break
        OI_STATS["ok"] += 1
        return oi[0] / oi[4] - 1, oi[0] / oi[24] - 1
    OI_STATS["ko"] += 1
    return None, None

# ---------------- INDICATEURS ----------------
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def atr(df, n=14):
    tr = pd.concat([df.h - df.l, (df.h - df.c.shift()).abs(),
                    (df.l - df.c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def tendance(df):
    c, e20, e50 = df.c, ema(df.c, 20), ema(df.c, 50)
    if c.iloc[-1] > e50.iloc[-1] and e20.iloc[-1] > e50.iloc[-1] and e20.iloc[-1] > e20.iloc[-5]:
        return "HAUSSIÈRE"
    if c.iloc[-1] < e50.iloc[-1] and e20.iloc[-1] < e50.iloc[-1] and e20.iloc[-1] < e20.iloc[-5]:
        return "BAISSIÈRE"
    return NEUTRE

def zones(df, a, k=3, lookback=150):
    """Zones S/R à partir des pivots H1 regroupés (largeur mini 0,3 ATR).
    Même calcul que Crypto Pépite (pivots à k bougies, zone plafonnée à ZONE_LARGEUR_MAX ATR),
    écrit en calcul vectorisé : indispensable ici, la fonction est appelée bien plus souvent."""
    d = df.tail(lookback)
    h, l = d.h.values, d.l.values
    n = len(h)
    if n < 2 * k + 1:
        return []
    fen = np.lib.stride_tricks.sliding_window_view
    idx = np.arange(k, n - k)
    hauts = idx[h[k:n - k] == fen(h, 2 * k + 1).max(axis=1)]
    bas = idx[l[k:n - k] == fen(l, 2 * k + 1).min(axis=1)]
    pts = sorted([(float(h[i]), int(i)) for i in hauts] + [(float(l[i]), int(i)) for i in bas])
    clusters = []
    for p in pts:
        if clusters and p[0] - clusters[-1][-1][0] <= 0.5 * a \
                and p[0] - clusters[-1][0][0] <= ZONE_LARGEUR_MAX * a:
            clusters[-1].append(p)
        else: clusters.append([p])
    out = []
    for c in clusters:
        prix, ix = [x for x, _ in c], [i for _, i in c]
        lo, hi = min(prix), max(prix)
        if hi - lo < 0.3 * a:
            m = (lo + hi) / 2; lo, hi = m - 0.15 * a, m + 0.15 * a
        out.append(dict(lo=lo, hi=hi, touches=len(c), age_h=n - 1 - min(ix), dernier_h=n - 1 - max(ix)))
    return out

QUALITE_VIDE = dict(rejet_confirme=None, body_ratio=np.nan, wick_ratio=np.nan, close_pos=np.nan)

def bougie_rejet(b, z, sens, vol_ratio):
    """V6.1 : la bougie M15 clôturée montre-t-elle un vrai rejet de la zone ?
    close_pos = position de la clôture dans la bougie, dans le sens du trade (1 = extrême favorable).
    wick_ratio = mèche de rejet / taille de la bougie."""
    rng = b.h - b.l
    if rng <= 0:
        return dict(rejet_confirme=False, body_ratio=0.0, wick_ratio=0.0, close_pos=0.5)
    body = abs(b.c - b.o) / rng
    if sens == "LONG":
        wick = (min(b.o, b.c) - b.l) / rng
        cpos = (b.c - b.l) / rng
        ok = b.l <= z["hi"] and b.c > z["hi"] and b.c > b.o and cpos >= CLOSE_POS_MIN
    else:
        wick = (b.h - max(b.o, b.c)) / rng
        cpos = (b.h - b.c) / rng
        ok = b.h >= z["lo"] and b.c < z["lo"] and b.c < b.o and cpos >= CLOSE_POS_MIN
    if REJET_VOLUME_OBLIGATOIRE:
        ok = ok and vol_ratio >= REJET_VOLUME_MIN
    return dict(rejet_confirme=bool(ok), body_ratio=round(body, 2),
                wick_ratio=round(wick, 2), close_pos=round(cpos, 2))

def vwap_jour(m15):
    d = m15.copy(); d["j"] = d.t // 86_400_000
    d = d[d.j == d.j.iloc[-1]]
    tp = (d.h + d.l + d.c) / 3
    return (tp * d.v).sum() / d.v.sum() if d.v.sum() > 0 else np.nan

# ---------------- FILTRE BTC ----------------
def contexte_btc():
    global BTC_CTX
    h4, h1, m15 = klines("BTCUSDT", "240"), klines("BTCUSDT", "60"), klines("BTCUSDT", "15")
    if any(x is None or len(x) < 60 for x in (h4, h1, m15)):
        print("⚠️ Contexte BTC indisponible : filtre BTC désactivé pour ce scan")
        return
    choc = m15.c.iloc[-1] / m15.c.iloc[-5] - 1
    t4, t1 = tendance(h4), tendance(h1)
    ut_neutres = [nom for nom, t in (("H4", t4), ("H1", t1)) if t == NEUTRE]
    BTC_CTX = dict(t4=t4, t1=t1, h1=h1, choc=choc,
                   n_neutre=len(ut_neutres), ut_neutres=ut_neutres)
    alerte = "  ⚡ CHOC" if abs(choc) >= BTC_CHOC else ""
    print(f"Contexte BTC : H4 {t4} | H1 {t1} | 1h {choc*100:+.2f} %{alerte}")

def alerte_btc_neutre():
    if not BTC_FILTRE or BTC_CTX is None or BTC_CTX["n_neutre"] == 0:
        return ""
    if BTC_CTX["n_neutre"] == 2:
        return ("⚠️ BTC SANS DIRECTION (H4 + H1 neutres) : marché indécis, faux départs fréquents.\n"
                f"   → Score mini relevé à {SCORE_MIN_BTC_NEUTRE}, {MAX_NOW_BTC_NEUTRE} seul TRADE NOW autorisé. "
                "Privilégie les setups de range.")
    ut = BTC_CTX["ut_neutres"][0]
    return (f"⚠️ BTC neutre en {ut} : direction partielle, réduis l'exposition "
            f"(malus -{BTC_NEUTRE_1UT} pondéré par la corrélation).")

def resume_btc():
    if BTC_CTX is None:
        return "₿ BTC : tendance indisponible"
    fl = {"HAUSSIÈRE": "↗️", "BAISSIÈRE": "↘️", NEUTRE: "➡️"}
    t4, t1, choc = BTC_CTX["t4"], BTC_CTX["t1"], BTC_CTX["choc"]
    ligne = f"₿ BTC : H4 {t4} {fl.get(t4, '')} | H1 {t1} {fl.get(t1, '')} | 1h {choc*100:+.2f} %"
    if abs(choc) >= BTC_CHOC: ligne += " ⚡ CHOC"
    return ligne

def correlation_btc(h1):
    if BTC_CTX is None: return np.nan
    m = pd.merge(h1[["t", "c"]], BTC_CTX["h1"][["t", "c"]], on="t", suffixes=("", "_btc")).tail(49)
    if len(m) < 25: return np.nan
    return m.c.pct_change().corr(m.c_btc.pct_change())

def filtre_btc(sens, corr, setup_type=""):
    """Renvoie (points score, forcer WAIT ?, texte rapport, nb d'UT où BTC est contre)."""
    if not BTC_FILTRE or BTC_CTX is None:
        return 0, False, "désactivé", 0
    contre = "BAISSIÈRE" if sens == "LONG" else "HAUSSIÈRE"
    pour   = "HAUSSIÈRE" if sens == "LONG" else "BAISSIÈRE"
    tfs = (BTC_CTX["t4"], BTC_CTX["t1"])
    n_contre, n_pour, n_neutre = tfs.count(contre), tfs.count(pour), tfs.count(NEUTRE)
    choc = BTC_CTX["choc"]
    choc_contre = (sens == "LONG" and choc <= -BTC_CHOC) or (sens == "SHORT" and choc >= BTC_CHOC)
    cassure = "Cassure" in setup_type

    c_ok = not pd.isna(corr)
    poids = 1.0 if (not c_ok or corr >= CORR_FORTE) else 0.5 if corr >= CORR_FAIBLE else 0.0

    pts = -BTC_MALUS_FORT if n_contre == 2 else -BTC_MALUS_MOYEN if n_contre == 1 \
          else BTC_BONUS if n_pour == 2 else 0
    pts_neutre = 0
    if n_neutre:
        pts_neutre = -(BTC_NEUTRE_2UT if n_neutre == 2 else BTC_NEUTRE_1UT)
        if cassure: pts_neutre -= BTC_NEUTRE_CASSURE
    pts = round((pts + pts_neutre) * poids)
    wait = ((BTC_WAIT_TENDANCE and n_contre == 2) or choc_contre) and (not c_ok or corr >= CORR_WAIT)

    if n_contre == 2:   etat = "BTC contre le trade (H4 + H1)"
    elif n_contre == 1: etat = "BTC contre le trade sur une UT"
    elif n_pour == 2:   etat = "BTC dans le sens du trade"
    elif n_neutre == 2: etat = "BTC sans direction (H4 + H1 neutres)"
    elif n_pour == 1:   etat = f"BTC dans le sens en {'H4' if tfs[0] == pour else 'H1'}, neutre sur l'autre UT"
    else:               etat = "BTC neutre"
    if n_contre == 1 and n_neutre == 1: etat += ", neutre sur l'autre"
    if n_neutre and cassure: etat += " — cassure pénalisée"
    if choc_contre: etat += f" + choc BTC {choc*100:+.2f} % sur 1h"
    corr_txt = "n/d" if not c_ok else f"{corr:.2f}"
    if poids == 0: etat += " — alt décorrélée, malus sans effet"
    elif poids == 0.5: etat += " — corrélation moyenne, effet réduit"
    impact = f"impact score {pts:+d}" if BTC_IMPACT_SCORE else f"impact score {pts:+d} (journalisé, non appliqué)"
    return pts, wait, f"{etat} | corrélation H1 {corr_txt} | {impact}", n_contre

def rel_btc(t, sens):
    if t == NEUTRE: return "neutre"
    pour = "HAUSSIÈRE" if sens == "LONG" else "BAISSIÈRE"
    return "sens" if t == pour else "contre"

def btc_detail(sens):
    """V6 : position de BTC par rapport au trade, en H4 puis H1 (ex. « sens-neutre »)."""
    if BTC_CTX is None: return "n/d"
    return f"{rel_btc(BTC_CTX['t4'], sens)}-{rel_btc(BTC_CTX['t1'], sens)}"

def contexte_btc_label(sens):
    if BTC_CTX is None: return "n/d"
    tfs = (BTC_CTX["t4"], BTC_CTX["t1"])
    if ("BAISSIÈRE" if sens == "LONG" else "HAUSSIÈRE") in tfs: return "contre"
    if ("HAUSSIÈRE" if sens == "LONG" else "BAISSIÈRE") in tfs: return "sens"
    return "neutre"

# ---------------- INTERPRÉTATION ----------------
def interp_oi(ch, oi):
    if oi is None: return "OI indisponible"
    if ch > 0 and oi > 0: return "Prix ↑ + OI ↑ : nouvelles positions, mouvement soutenu"
    if ch > 0 and oi <= 0: return "Prix ↑ + OI ↓ : short covering probable"
    if ch <= 0 and oi > 0: return "Prix ↓ + OI ↑ : nouveaux shorts probables"
    return "Prix ↓ + OI ↓ : désengagement / liquidations"

def interp_funding(f):
    if pd.isna(f): return "funding indisponible"
    if f > 0.0005: return "funding élevé : longs chargés (risque de flush)"
    if f < -0.0005: return "funding très négatif : shorts chargés (risque de squeeze)"
    return "funding neutre"

SC_COLS = ["sc_tendance", "sc_timing", "sc_volume", "sc_oi", "sc_rr", "sc_liquidite", "sc_malus", "sc_btc"]

def score(s, t4, t1, vol_ratio, oi4, ch4, rr, dist, row, r1):
    """V6 : renvoie (score total, détail par composante) pour pouvoir analyser le score."""
    d = 1 if s["sens"] == "LONG" else -1
    want = "HAUSSIÈRE" if d == 1 else "BAISSIÈRE"
    c = dict.fromkeys(SC_COLS[:-1], 0.0)
    c["sc_tendance"] = (15 if t4 == want else 7 if t4 == NEUTRE else 0) + \
                       (10 if t1 == want else 5 if t1 == NEUTRE else 0)
    c["sc_timing"] = max(0, 20 * (1 - dist))
    c["sc_volume"] = max(0, min(15, 15 * (vol_ratio - 0.8) / 0.8))
    if oi4 is None: c["sc_oi"] = 5
    else:
        p, o = ch4 * d > 0, oi4 > 0
        c["sc_oi"] = 15 if (p and o) else 10 if (not p and not o) else 5 if p else 0
    c["sc_rr"] = 15 if rr >= 2.5 else 12 if rr >= 2 else 8 if rr >= RR_MIN else 0
    to = row.turnover24h
    c["sc_liquidite"] = 10 if to >= 50e6 else 7 if to >= 15e6 else 4
    m = 0
    if row.spread > 0.0008: m -= 3
    if not pd.isna(row.fundingRate) and d * row.fundingRate > 0.0005: m -= 10
    if (d == 1 and r1 > 75) or (d == -1 and r1 < 25): m -= 10
    c["sc_malus"] = m
    total = int(max(0, min(100, round(sum(c.values())))))
    return total, {k: round(float(v), 1) for k, v in c.items()}

def arrondi(x, tick):
    return round(round(x / tick) * tick, 10) if tick else x

def sizing(e, sl, inf):
    dist = abs(e - sl)
    q = RISQUE / (dist + 2 * FRAIS_TAKER * e)
    step = inf.get("step")
    if step: q = math.floor(q / step) * step
    notional = q * e
    lev = max(1, math.ceil(notional / MARGE_CIBLE))
    return dict(q=q, notional=notional, lev=lev, marge=notional / lev,
                risque=q * dist + 2 * FRAIS_TAKER * notional,
                trop_petit=bool(inf.get("minq") and q < inf["minq"]))

# ---------------- CONTEXTE H4 / H1 (calculé une fois par bougie H1 et par paire) ----------------
_KC, _CTX = {}, {}
FORCE = {}
T_PULL, T_CASS, T_RANGE = "Pullback tendance H4", "Cassure + retest H1", "Rebond bas de range"

# Compteurs cumulés (scans x paires) : où les candidats s'arrêtent-ils ?
DIAG = dict.fromkeys(["a_pullback : prix possible sur la moyenne 20 H4", "b_pullback : rejet M15",
                      "c_cassure : cassure H1 valide en attente de retest", "d_cassure : rejet M15",
                      "e_range : altcoin en range", "f_range : rejet M15 en bas de range",
                      "g_bougie pas assez franche", "h_BTC défavorable ou choc",
                      "i_frais trop lourds", "j_TRADE NOW"], 0)

def kl(sym, iv):
    """klines mémorisées pour la durée d'un scan (évite de relire 2 fois les mêmes bougies)."""
    k = (sym, iv)
    if k not in _KC:
        _KC[k] = klines(sym, iv)
    return _KC[k]

def perf(sym, heures):
    h1 = kl(sym, "60")
    if h1 is None or len(h1) <= heures:
        return None
    return h1.c.iloc[-1] / h1.c.iloc[-1 - heures] - 1

def preparer_scan(syms):
    """Vide la mémoire des bougies et calcule l'écart de performance avec BTC sur FORCE_H heures
    (information journalisée, pas un filtre)."""
    global FORCE
    _KC.clear()
    FORCE = {}
    pb = perf("BTCUSDT", FORCE_H)
    if pb is None:
        return
    for s_ in syms:
        if s_ == "BTCUSDT":
            continue
        p = perf(s_, FORCE_H)
        if p is not None:
            FORCE[s_] = p - pb

def niveau_casse(h1, a1):
    """Setup 2 : cherche, dans les RETEST_BARRES dernières bougies H1, une cassure valide d'une
    résistance (zone calculée sur les bougies d'AVANT la cassure). Renvoie la zone ou None."""
    c, v, t = h1.c.values, h1.v.values, h1.t.values
    n = len(c)
    for i in range(n - 1, max(n - 1 - RETEST_BARRES, CASSURE_RECUL + 20), -1):
        avant = c[i - CASSURE_RECUL:i].max()
        if c[i] <= avant:
            continue                                   # pas de nouvelle clôture au-dessus
        vm = v[i - 20:i].mean()
        if vm <= 0 or v[i] < CASSURE_VOL * vm:
            continue                                   # cassure sans volume
        cands = [z for z in zones(h1.iloc[:i], a1)
                 if z["touches"] >= ZONE_TESTS_MIN and avant <= z["hi"] < c[i]
                 and z["dernier_h"] <= CASSURE_TEST_H]
        if not cands:
            continue
        z = max(cands, key=lambda z: z["hi"])
        if (c[i + 1:] <= z["lo"]).any():
            continue                                   # la cassure n'a pas tenu
        return dict(z, t_cassure=float(t[i]), vol_x=float(v[i] / vm), h_depuis=n - 1 - i)
    return None

def contexte(sym):
    """Ce qui ne change qu'une fois par heure : tendance H4, zone de pullback, cassure en attente
    de retest, zones du range. Mémorisé par paire et par bougie H1."""
    h4, h1 = kl(sym, "240"), kl(sym, "60")
    if any(x is None or len(x) < 60 for x in (h4, h1)):
        return None
    cle = (sym, h1.t.iat[-1], len(h1), h4.t.iat[-1])
    if cle in _CTX:
        return _CTX[cle]
    if len(_CTX) > 50_000:
        _CTX.clear()
    a1 = float(atr(h1).iloc[-1])
    t4 = tendance(h4)
    ctx = dict(a1=a1, t4=t4, pull=None, cass=None, zs=None)
    if a1 > 0:
        if SETUP_PULLBACK and t4 == "HAUSSIÈRE":
            m20 = float(ema(h4.c, 20).iloc[-1])
            if h1.h.tail(PULL_HAUT_H).max() >= m20 + PULL_HAUT * a1:
                ctx["pull"] = dict(lo=m20 - PULL_TOL * a1, hi=m20 + PULL_TOL * a1, m20=m20,
                                   m50=float(ema(h4.c, 50).iloc[-1]))
        if SETUP_CASSURE and t4 != "BAISSIÈRE":
            ctx["cass"] = niveau_casse(h1, a1)
        if SETUP_RANGE and t4 == NEUTRE:
            ctx["zs"] = zones(h1, a1)
    _CTX[cle] = ctx
    return ctx

def prefiltre(sym):
    ctx = contexte(sym) if sym != "BTCUSDT" else None
    return bool(ctx and (ctx["pull"] or ctx["cass"] or ctx["zs"]))

def franche(q):
    """Bougie de rejet franche : clôture dans le haut de la bougie OU gros corps."""
    return q["close_pos"] >= CLOSE_POS_FORT or q["body_ratio"] >= BODY_FORT

# ---------------- ANALYSE D'UNE PAIRE ----------------
VIDE = dict(rejet_confirme=None, body_ratio=np.nan, wick_ratio=np.nan, close_pos=np.nan,
            touches_zone=np.nan, age_zone_h=np.nan, dernier_test_h=np.nan, largeur_zone_ATR=np.nan)

def _zone_infos(z, a1):
    return dict(touches_zone=z["touches"], age_zone_h=z["age_h"], dernier_test_h=z["dernier_h"],
                largeur_zone_ATR=(z["hi"] - z["lo"]) / a1)

def analyse(row, inf):
    """Les trois setups, LONG uniquement. Déclencheur commun : rejet M15 de la zone."""
    sym, px = row.symbol, row.lastPrice
    if not prefiltre(sym):
        return []
    ctx = contexte(sym)
    h1, m15 = kl(sym, "60"), kl(sym, "15")
    if m15 is None or len(m15) < 60:
        return []
    a1, t4 = ctx["a1"], ctx["t4"]
    tick = inf.get("tick")
    A = lambda x: arrondi(x, tick)
    b = m15.iloc[-1]
    vol_moy = m15.v.iloc[-21:-1].mean()
    vol_ratio = b.v / vol_moy if vol_moy > 0 else 0.0
    setups = []

    # ---- Setup 1 : pullback sur la moyenne 20 H4 ----
    z = ctx["pull"]
    if z:
        DIAG["a_pullback : prix possible sur la moyenne 20 H4"] += 1
        q = bougie_rejet(b, z, "LONG", vol_ratio)
        if q["rejet_confirme"]:
            DIAG["b_pullback : rejet M15"] += 1
            creux = min(m15.l.tail(PULL_CREUX_M15).min(), z["lo"])
            setups.append(dict(VIDE, **q, type=T_PULL, zone=z, sl=creux - SL_MARGE * a1, cible=None,
                               trig=z["hi"], btc="tendance",
                               pourquoi_ok="repli sur la moyenne 20 H4 rejeté en M15",
                               preuves=[f"Tendance H4 haussière : moyenne 20 ({A(z['m20'])}) au-dessus "
                                        f"de la 50 ({A(z['m50'])}) et montante",
                                        f"Repli dans la zone de la moyenne 20 H4 ({A(z['lo'])} – {A(z['hi'])})",
                                        f"Rejet M15 : mèche dans la zone, clôture à {q['close_pos']*100:.0f} % "
                                        f"de la bougie, corps {q['body_ratio']*100:.0f} %"]))

    # ---- Setup 2 : cassure + retest ----
    z = ctx["cass"]
    if z and b.t >= z["t_cassure"] + 3_600_000:          # la bougie M15 est postérieure à la cassure
        DIAG["c_cassure : cassure H1 valide en attente de retest"] += 1
        q = bougie_rejet(b, z, "LONG", vol_ratio)
        if q["rejet_confirme"]:
            DIAG["d_cassure : rejet M15"] += 1
            setups.append(dict(VIDE, **q, **_zone_infos(z, a1), type=T_CASS, zone=z,
                               sl=min(z["lo"], b.l) - SL_MARGE * a1, cible=None, trig=z["hi"], btc="tendance",
                               pourquoi_ok="ancienne résistance cassée puis retestée, rejet M15",
                               preuves=[f"Résistance H1 {A(z['lo'])} – {A(z['hi'])} ({z['touches']} tests) "
                                        f"cassée il y a {z['h_depuis'] + 1} h, volume x{z['vol_x']:.1f}",
                                        "Depuis, aucune clôture H1 n'est repassée sous la zone",
                                        f"Retest : rejet M15, clôture à {q['close_pos']*100:.0f} % de la bougie, "
                                        f"corps {q['body_ratio']*100:.0f} %"]))

    # ---- Setup 3 : rebond en bas de range ----
    zs = ctx["zs"]
    if zs:
        sup = [z for z in zs if z["hi"] < b.c]
        res = [z for z in zs if z["lo"] > b.c]
        if sup and res:
            s_, r_ = max(sup, key=lambda z: z["hi"]), min(res, key=lambda z: z["lo"])
            haut = r_["lo"] - s_["hi"]
            if s_["touches"] >= ZONE_TESTS_MIN and r_["touches"] >= RANGE_RES_TESTS \
                    and haut >= RANGE_MIN_ATR * a1:
                DIAG["e_range : altcoin en range"] += 1
                q = bougie_rejet(b, s_, "LONG", vol_ratio)
                if q["rejet_confirme"] and b.c <= s_["hi"] + RANGE_BAS * haut:
                    DIAG["f_range : rejet M15 en bas de range"] += 1
                    setups.append(dict(VIDE, **q, **_zone_infos(s_, a1), type=T_RANGE, zone=s_,
                                       sl=min(s_["lo"], b.l) - SL_MARGE * a1,
                                       cible=(s_["hi"] + r_["lo"]) / 2, trig=s_["hi"], btc="range",
                                       sup=[s_], res=[r_],
                                       pourquoi_ok="rejet M15 du support en bas de range",
                                       preuves=[f"Altcoin sans tendance en H4, range H1 de {haut / a1:.1f} ATR",
                                                f"Support {A(s_['lo'])} – {A(s_['hi'])} ({s_['touches']} tests), "
                                                f"résistance {A(r_['lo'])} – {A(r_['hi'])} ({r_['touches']} tests)",
                                                f"Rejet M15 du support, clôture à {q['close_pos']*100:.0f} % "
                                                f"de la bougie, corps {q['body_ratio']*100:.0f} %"]))
    if not setups:
        return []

    e = float(b.c)
    t1, t15, r1 = tendance(h1), tendance(m15), rsi(h1.c).iloc[-1]
    corr = correlation_btc(h1)
    btc4 = BTC_CTX["t4"] if BTC_CTX is not None else None
    choc = BTC_CTX is not None and BTC_CTX["choc"] <= -BTC_CHOC
    cands = []
    for s in setups:
        sl = float(s["sl"])
        rd = e - sl
        if rd <= 0:
            continue
        rr = TP_R if s["cible"] is None else min(TP_R, (s["cible"] - e) / rd)
        tp = e + rr * rd
        frais = 2 * FRAIS_TAKER * e / rd
        if abs(row.price24hPcnt) > MAX_MOVE_24H:
            dec, why = "NO TRADE", "mouvement 24 h excessif"
        elif rr < RR_MIN:
            dec, why = "NO TRADE", f"milieu du range trop proche ({rr:.2f} R < {RR_MIN} R)"
        elif choc:
            dec, why = "WAIT", "choc BTC baissier"
            DIAG["h_BTC défavorable ou choc"] += 1
        elif s["btc"] == "tendance" and BTC_BAISSIER_BLOQUE and btc4 == "BAISSIÈRE":
            dec, why = "WAIT", "BTC baissier en H4"
            DIAG["h_BTC défavorable ou choc"] += 1
        elif s["btc"] == "range" and RANGE_BTC_RANGE and btc4 != NEUTRE:
            dec, why = "WAIT", "BTC pas en range en H4"
            DIAG["h_BTC défavorable ou choc"] += 1
        elif FILTRE_BOUGIE and not franche(s):
            dec, why = "WAIT", "bougie de rejet pas assez franche"
            DIAG["g_bougie pas assez franche"] += 1
        elif frais > FRAIS_MAX_R:
            dec, why = "WAIT", f"frais trop lourds (> {FRAIS_MAX_R} R) : SL trop serré"
            DIAG["i_frais trop lourds"] += 1
        else:
            dec, why = "TRADE NOW", s["pourquoi_ok"]
            DIAG["j_TRADE NOW"] += 1
        base = dict(sup=[], res=[])
        base.update(s)
        cands.append(dict(base, sens="LONG", entry=e, sl=sl, dir="haut", deja=True,
                          symbol=sym, px=px, tp=tp, tp_theorique=False, rr=rr,
                          dist=abs(px - e) / a1, decision=dec, pourquoi=why, score=0,
                          t4=t4, t1=t1, t15=t15, vol_ratio=vol_ratio,
                          oi4=None, oi24=None, ch4=0.0, funding=row.fundingRate, rsi_h1=r1,
                          vwap=vwap_jour(m15), atr_h1=a1, turnover=row.turnover24h, spread=row.spread,
                          ch24=row.price24hPcnt, inf=inf, corr_btc=corr, btc_pts=0, btc_txt="",
                          btc_contre=0, force=FORCE.get(sym), rang=None, frais_r=frais,
                          **dict.fromkeys(SC_COLS, 0.0)))
    return cands

# ---------------- RAPPORT ----------------
def fz(z, t): return f"{arrondi(z['lo'], t)} – {arrondi(z['hi'], t)} ({z['touches']} tests)"

def rapport(c):
    t = c["inf"].get("tick")
    e, sl, tp = arrondi(c["entry"], t), arrondi(c["sl"], t), arrondi(c["tp"], t)
    sz = sizing(e, sl, c["inf"])
    rng = ""
    if c["t1"] == NEUTRE and c["sup"] and c["res"]:
        lo, hi = c["sup"][0]["lo"], c["res"][0]["hi"]
        rng = f"\nRange H1 : bas {fz(c['sup'][0], t)} | haut {fz(c['res'][0], t)} | prix à {100*(c['px']-lo)/(hi-lo):.0f} % du range"
    src = OI_SOURCE[0] if OI_SOURCE else "—"
    oi_txt = f"n/d (paire absente de {src})" if c["oi4"] is None else \
             f"{c['oi4']*100:+.1f} % (4h) / {c['oi24']*100:+.1f} % (24h)"
    ordre = "Market" if c["decision"] == "TRADE NOW" else "Conditional (déclenchement au niveau d'entrée)"
    frais_r = 2 * FRAIS_TAKER * e / abs(e - sl) if e != sl else 0
    rejet = {True: "confirmé ✅", False: "non confirmé"}.get(c["rejet_confirme"], "n/a")
    return f"""
══════════════════════════════════════════════
{c['symbol']}  |  Prix {c['px']}  |  Score {c['score']}/100  |  {c['decision']}
══════════════════════════════════════════════
Tendance H4 : {c['t4']} | H1 : {c['t1']} | M15 : {c['t15']}
Supports    : {' | '.join(fz(z, t) for z in c['sup']) or 'aucun identifié'}
Résistances : {' | '.join(fz(z, t) for z in c['res']) or 'aucune identifiée'}{rng}
VWAP jour : {arrondi(c['vwap'], t)} | RSI H1 : {c['rsi_h1']:.0f} | ATR H1 : {c['atr_h1']:.6g}
Volume M15 : x{c['vol_ratio']:.2f} la moyenne 20 | Volume 24h : {c['turnover']/1e6:.1f} M USDT | Variation 24h : {c['ch24']*100:+.1f} %
OI ({src}) : {oi_txt} | Funding Zoomex : {c['funding']*100:.4f} %
→ {interp_oi(c['ch4'], c['oi4'])} ; {interp_funding(c['funding'])}
Filtre BTC : {c['btc_txt']}

Sens : {c['sens']} | Setup : {c['type']}
Déclencheur : clôture M15 {'au-dessus' if c['dir']=='haut' else 'en dessous'} de {arrondi(c['trig'], t)}
Ordre Zoomex : {ordre}
Entrée : {e} | SL : {sl} | TP : {tp}{' (théorique 2R, pas de zone identifiée)' if c['tp_theorique'] else ''}
RR : {c['rr']:.2f} | Frais aller-retour ≈ {frais_r:.2f} R
Capital : {CAPITAL:.0f} USDT | Risque visé : {RISQUE} USDT (frais inclus)
Quantité : {sz['q']:.6g} tokens | Notionnel : {sz['notional']:.2f} USDT
Levier : x{sz['lev']} | Marge ≈ {sz['marge']:.2f} USDT | Risque réel au SL ≈ {sz['risque']:.2f} USDT{'  ⚠️ quantité < minimum Zoomex' if sz['trop_petit'] else ''}
Alerte TradingView : M15 — croisement vers le {c['dir']} de {arrondi(c['trig'], t)} — « Une fois par clôture de barre »
Invalidation : clôture H1 {'sous' if c['sens']=='LONG' else 'au-dessus de'} {sl}
Rejet M15 : {rejet} | clôture à {c['close_pos']*100 if c['close_pos'] == c['close_pos'] else 0:.0f} % | mèche {c['wick_ratio']*100 if c['wick_ratio'] == c['wick_ratio'] else 0:.0f} % | volume x{c['vol_ratio']:.2f}
Zone : {c['touches_zone']} tests | âge {c['age_zone_h']} h | dernier test il y a {c['dernier_test_h']} h
BTC H4-H1 par rapport au trade : {btc_detail(c['sens'])}
Pourquoi maintenant : {c['pourquoi']} ; distance à l'entrée = {c['dist']:.2f} ATR H1
⚠️ News / macro NON vérifiées par le script : contrôle avant d'entrer."""

# ---------------- TELEGRAM ----------------
def telegram(texte, html=False):
    """html=True : mise en forme Telegram (gras, <code> copiable d'un toucher)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("(Telegram non configuré : message non envoyé)")
        return
    morceaux, bloc = [], ""
    for ligne in texte.split("\n"):
        if len(bloc) + len(ligne) + 1 > 4000:
            morceaux.append(bloc); bloc = ""
        bloc += ligne + "\n"
    if bloc.strip(): morceaux.append(bloc)
    for m in morceaux:
        try:
            data = dict(chat_id=TELEGRAM_CHAT_ID, text=m, disable_web_page_preview=True)
            if html: data["parse_mode"] = "HTML"
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              data=data, timeout=15)
            if r.status_code == 400 and html:
                # V7.3 : mise en forme refusée -> renvoi en texte simple (le message arrive quand même)
                print(f"⚠️ Telegram : mise en forme refusée ({r.text[:120]}), renvoi en texte simple")
                data.pop("parse_mode", None)
                data["text"] = unescape(re.sub(r"<[^>]+>", "", m))
                r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                  data=data, timeout=15)
            if r.status_code != 200:
                print(f"⚠️ Telegram : HTTP {r.status_code} {r.text[:200]}")
        except Exception as ex:
            print(f"⚠️ Telegram injoignable ({type(ex).__name__})")
        time.sleep(0.5)

def charger_etat():
    try:
        with open(ETAT_FICHIER, encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {}

def sauver_etat(etat):
    limite = time.time() - 24 * 3600
    etat = {k: v for k, v in etat.items() if v >= limite}
    with open(ETAT_FICHIER, "w", encoding="utf-8") as f: json.dump(etat, f)

def lien_tv(r):
    return f"https://www.tradingview.com/chart/?symbol={TV_PREFIXE}{r['symbol']}{TV_SUFFIXE}&interval=15"

def ligne_pepite(r):
    t = r["inf"].get("tick")
    return f"PEPITE;{r['symbol']};{r['sens']};{arrondi(r['entry'], t)};{arrondi(r['sl'], t)};{arrondi(r['tp'], t)}"

def fmt_num(x, pas=None):
    """Nombre prêt à coller dans Zoomex : arrondi au pas, jamais en notation scientifique."""
    if pas:
        dec = max(0, -Decimal(str(pas)).normalize().as_tuple().exponent)
        return f"{x:.{dec}f}"
    return f"{x:.10f}".rstrip("0").rstrip(".")

def ticket(r):
    """V6.6 : ticket court, valeurs copiables d'un toucher (police monospace)."""
    t, step = r["inf"].get("tick"), r["inf"].get("step")
    e, sl, tp = arrondi(r["entry"], t), arrondi(r["sl"], t), arrondi(r["tp"], t)
    sz = sizing(e, sl, r["inf"])
    base = escape(r["symbol"][:-4])
    sens = "🟢 LONG" if r["sens"] == "LONG" else "🔴 SHORT"
    txt = (f"🎫🎯 <b>TRIO ALT · TICKET {escape(r['symbol'])} —</b>\n"
           f"<b>{sens}</b>\n"
           f"\n"
           f"Paire : <code>{base}</code>\n"
           f"Quantité : <code>{fmt_num(sz['q'], step)}</code> {base}\n"
           f"Entrée : <code>{fmt_num(e, t)}</code>\n"
           f"SL : <code>{fmt_num(sl, t)}</code>\n"
           f"TP : <code>{fmt_num(tp, t)}</code>\n"
           f"Valeur : <code>{sz['notional']:.2f}</code> USDT\n"
           f"\n"
           f"Marge ≈ {sz['marge']:.2f} USDT · risque ≈ {sz['risque']:.2f} USDT")
    if sz["trop_petit"]:
        txt += "\n⚠️ Quantité sous le minimum Zoomex : trade impossible tel quel"
    return txt

FRAIS_ALERTE_R = 0.15   # V7.0 : au-delà, la fiche signale des frais lourds (non bloquant)

def fiche(r):
    """Fiche d'analyse Trio Alt : quel setup, pourquoi c'est un TRADE NOW, contexte BTC."""
    E = lambda x: escape(str(x))
    t = r["inf"].get("tick")
    sl, tp = arrondi(r["sl"], t), arrondi(r["tp"], t)
    fl = {"HAUSSIÈRE": "↗️", "BAISSIÈRE": "↘️", NEUTRE: "➡️"}
    court = {"HAUSSIÈRE": "haussière", "BAISSIÈRE": "baissière", NEUTRE: "range"}
    force = f"{r['force']*100:+.1f} %" if r.get("force") is not None else "n/d"
    etoile = "⭐ " if BTC_CTX is not None and BTC_CTX["t4"] == NEUTRE else ""
    btc = ("₿ BTC : indisponible" if BTC_CTX is None else
           f"{etoile}₿ BTC : H4 {court[BTC_CTX['t4']]} {fl[BTC_CTX['t4']]} | H1 {court[BTC_CTX['t1']]} "
           f"{fl[BTC_CTX['t1']]} | 1h {BTC_CTX['choc']*100:+.2f} %")
    cible = "milieu du range" if r["type"] == T_RANGE and r["rr"] < TP_R else f"plafond {TP_R:g} R"
    lignes = [
        f"🎯 <b>TRIO ALT — {E(r['symbol'])} — 🟢 LONG</b>",
        f"<i>{E(r['type'])} · prix {E(r['px'])} · V{VERSION} · {datetime.now(timezone.utc):%H:%M} UTC</i>",
        "",
        "<b>Pourquoi TRADE NOW</b>"]
    lignes += [f"✅ {E(p)}" for p in r["preuves"]]
    lignes += [
        f"✅ Frais : {r['frais_r']:.2f} R (max {FRAIS_MAX_R})",
        "",
        "<b>Contexte</b>",
        E(btc),
        f"{E(r['symbol'][:-4])} : H4 {court[r['t4']]} {fl[r['t4']]} | H1 {court[r['t1']]} {fl[r['t1']]} · "
        f"{E(force)} par rapport à BTC sur {FORCE_H // 24} j",
        f"🎯 TP {r['rr']:.1f} R ({cible}) : {E(tp)} · SL : {E(sl)}",
        f"24 h : {r['ch24']*100:+.1f} % · RSI H1 {r['rsi_h1']:.0f} · volume M15 x{r['vol_ratio']:.2f} · "
        f"{E(interp_funding(r['funding']))}",
        "",
        "⚠️ News / macro non vérifiées",
        f"📊 <a href=\"{E(lien_tv(r))}\">Graphique TradingView M15</a>",
    ]
    return "\n".join(lignes)

# ---------------- MES DÉCISIONS (V7.1) ----------------
MOTS_PRIS = ("pris", "prise", "pri", "in", "ok")
MOTS_NON = ("non", "pas", "passe", "skip", "no")

def _tg(methode, **params):
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{methode}", params=params, timeout=15)
        j = r.json()
        return j.get("result") if j.get("ok") else None
    except Exception:
        return None

def lire_decisions(j):
    """Lit les réponses « pris » / « non » envoyées sur Telegram depuis le dernier scan
    et les range dans le journal (colonnes ma_decision / ma_raison / date_decision)."""
    if not LIRE_DECISIONS or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return j, []
    maj = _tg("getUpdates", timeout=0, allowed_updates=json.dumps(["message", "channel_post"]))
    if not maj:
        return j, []
    notes = []
    reels = j[(j["type"] == "REEL")]
    symboles = set(reels["symbol"])
    for u in maj:
        m = u.get("message") or u.get("channel_post") or {}
        if str(m.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
            continue                                   # uniquement ta conversation
        texte = (m.get("text") or "").strip()
        mots = texte.split()
        if not mots:
            continue
        premier = mots[0].lower().strip(".,!:")
        if premier.startswith(MOTS_PRIS) and not premier.startswith("pas"):
            decision = "pris"
        elif premier.startswith(MOTS_NON):
            decision = "pas pris"
            if premier == "pas" and len(mots) > 1 and mots[1].lower().startswith("pris"):
                mots = mots[1:]
        else:
            continue
        reste = mots[1:]
        # Paire : dans la réponse (« pris COMP ») ou dans le message auquel tu réponds
        sym = None
        for w in reste[:2]:
            w2 = w.upper().strip(".,!:")
            for cand in (w2, w2 + "USDT"):
                if cand in symboles:
                    sym = cand
            if sym:
                reste = [x for x in reste if x != w]
                break
        if sym is None:
            cite = (m.get("reply_to_message") or {}).get("text") or ""
            trouve = re.findall(r"\b([A-Z0-9]{2,20}USDT)\b", cite)
            sym = next((x for x in trouve if x in symboles), None)
        reels = j[j["type"] == "REEL"]               # à jour (tient compte des réponses précédentes)
        cibles = reels[reels["ma_decision"] == ""] if sym is None else reels[reels["symbol"] == sym]
        if not len(cibles):
            notes.append(f"❓ Je n'ai pas trouvé d'alerte pour « {texte} »")
            continue
        i = cibles["ts"].astype(float).idxmax()     # l'alerte la plus récente
        raison = " ".join(reste).strip()
        j.loc[i, "ma_decision"] = decision
        j.loc[i, "ma_raison"] = raison
        j.loc[i, "date_decision"] = fmt_date(float(m.get("date", time.time())) * 1000)
        notes.append(f"📝 Noté : {j.loc[i, 'symbol']} — {decision}" + (f" ({raison})" if raison else ""))
    _tg("getUpdates", offset=maj[-1]["update_id"] + 1, timeout=0)   # messages marqués comme lus
    return j, notes

def cle_signal(r):
    return f"{r['symbol']}|{r['sens']}|{r['type']}"   # une alerte par paire et par sens toutes les 6 h

# ---------------- JOURNAL ----------------
STRATEGIES = {
    "sim_A": "A — TP / SL actuels",
    "sim_B": "B — SL à break-even dès +1 R",
    "sim_C": "C — SL à break-even dès +1,5 R",
    "sim_D": f"D — rien avant +1,5 R, puis SL technique (extrême des {TRAIL_N} dernières M15)",
    "sim_E": "E — 50 % à +1 R, reste au TP (SL inchangé)",
    "sim_F": "F — TP fixe 1,5 R",
    "sim_G": "G — TP fixe 2 R"}
SIM_COLS = list(STRATEGIES)
# type : REEL (TRADE NOW envoyé) ou FANTOME (suivi sans trade)
# statut : ATTENTE (fantôme pas encore déclenché) / EN_COURS / TP / SL / EXPIRE
#          NON_DECLENCHE / INVALIDE (SL avant l'entrée) / RATE (TP avant l'entrée) / PROMU
COLS_JOURNAL = ["id", "type", "version", "date_utc", "ts", "ts_entree", "symbol", "sens", "setup",
                "decision", "raison", "score", "entree", "px_signal", "ecart_entree_R", "sl", "tp", "rr",
                "btc_h4", "btc_h1", "btc_ctx", "btc_detail", "corr_btc", "btc_pts"] + SC_COLS + \
               ["rejet_confirme", "body_ratio", "wick_ratio", "close_pos", "vol_ratio", "dist_ATR",
                "touches_zone", "age_zone_h", "dernier_test_h", "largeur_zone_ATR",
                "statut", "date_sortie", "resultat_R", "frais_R", "resultat_net_R",
                "mfe_R", "mae_R", "duree_h", "backfill"] + SIM_COLS + ["sim_statut",
                "ma_decision", "ma_raison", "date_decision", "force_vs_btc"]
COLS_TEXTE = ["id", "type", "version", "date_utc", "symbol", "sens", "setup", "decision", "raison",
              "btc_h4", "btc_h1", "btc_ctx", "btc_detail", "rejet_confirme",
              "statut", "date_sortie", "backfill", "sim_statut",
              "ma_decision", "ma_raison", "date_decision"]
STATUTS_CLOS = ["TP", "SL", "EXPIRE"]

def charger_journal():
    try:
        j = pd.read_csv(JOURNAL)
    except Exception:
        j = pd.DataFrame(columns=COLS_JOURNAL)
    for c in COLS_JOURNAL:
        if c not in j: j[c] = np.nan
    for c in COLS_TEXTE:
        j[c] = j[c].astype(object).where(j[c].notna(), "").astype(str)
    for c in COLS_JOURNAL:
        if c not in COLS_TEXTE: j[c] = pd.to_numeric(j[c], errors="coerce")
    j.loc[j["type"] == "", "type"] = "REEL"
    j.loc[j["version"] == "", "version"] = "avant V6"
    m = j["ts_entree"].isna() & j["statut"].isin(["EN_COURS"] + STATUTS_CLOS)
    j.loc[m, "ts_entree"] = j.loc[m, "ts"]
    risque = (j["entree"] - j["sl"]).abs()
    m = j["frais_R"].isna() & risque.gt(0)
    j.loc[m, "frais_R"] = (2 * FRAIS_TAKER * j["entree"] / risque)[m].round(2)
    m = j["resultat_net_R"].isna() & j["resultat_R"].notna()
    j.loc[m, "resultat_net_R"] = (j["resultat_R"] - j["frais_R"].fillna(0))[m].round(2)
    return j[COLS_JOURNAL]

def ajouter_lignes(j, lignes):
    if not lignes: return j
    n = pd.DataFrame(lignes, columns=COLS_JOURNAL)
    return pd.concat([j, n], ignore_index=True) if len(j) else n

def ligne_journal(r, maintenant, type_, statut):
    t = r["inf"].get("tick")
    e, sl, tp = arrondi(r["entry"], t), arrondi(r["sl"], t), arrondi(r["tp"], t)
    risque = abs(e - sl)
    d = 1 if r["sens"] == "LONG" else -1
    ts = int(maintenant * 1000)
    actif = statut == "EN_COURS"
    lg = dict(
        id=cle_signal(r), type=type_, version=VERSION_LOGIQUE,
        date_utc=datetime.fromtimestamp(maintenant, timezone.utc).strftime("%Y-%m-%d %H:%M"),
        ts=ts, ts_entree=ts if actif else np.nan, symbol=r["symbol"], sens=r["sens"], setup=r["type"],
        decision=r["decision"], raison=r["pourquoi"], score=r["score"], entree=e, px_signal=r["px"],
        ecart_entree_R=round(d * (r["px"] - e) / risque, 2) if risque > 0 else np.nan,
        sl=sl, tp=tp, rr=round(r["rr"], 2),
        btc_h4=BTC_CTX["t4"] if BTC_CTX else "", btc_h1=BTC_CTX["t1"] if BTC_CTX else "",
        btc_ctx=contexte_btc_label(r["sens"]), btc_detail=btc_detail(r["sens"]),
        corr_btc=None if pd.isna(r["corr_btc"]) else round(float(r["corr_btc"]), 2),
        btc_pts=r["btc_pts"], statut=statut, date_sortie="", resultat_R=np.nan,
        frais_R=round(2 * FRAIS_TAKER * e / risque, 2) if risque > 0 else np.nan,
        resultat_net_R=np.nan, mfe_R=0.0 if actif else np.nan, mae_R=0.0 if actif else np.nan,
        duree_h=np.nan, backfill="", sim_statut="",
        rejet_confirme={True: "oui", False: "non"}.get(r.get("rejet_confirme"), ""),
        body_ratio=r.get("body_ratio"), wick_ratio=r.get("wick_ratio"), close_pos=r.get("close_pos"),
        vol_ratio=round(float(r["vol_ratio"]), 2), dist_ATR=round(float(r["dist"]), 2),
        touches_zone=r.get("touches_zone"), age_zone_h=r.get("age_zone_h"),
        dernier_test_h=r.get("dernier_test_h"),
        largeur_zone_ATR=round(float(r.get("largeur_zone_ATR", np.nan)), 2))
    for c in SC_COLS + SIM_COLS:
        lg[c] = r.get(c, np.nan)
    lg["force_vs_btc"] = None if r.get("force") is None else round(float(r["force"]), 4)
    return lg

def ajouter_reels(j, signaux, maintenant):
    for r in signaux:   # un fantôme ouvert identique devient « PROMU » (il est désormais suivi en réel)
        m = (j["type"] == "FANTOME") & j["statut"].isin(["ATTENTE", "EN_COURS"]) & \
            (j["symbol"] == r["symbol"]) & (j["sens"] == r["sens"]) & (j["setup"] == r["type"])
        j.loc[m, "statut"] = "PROMU"
    return ajouter_lignes(j, [ligne_journal(r, maintenant, "REEL", "EN_COURS") for r in signaux])

def ajouter_fantomes(j, candidats, maintenant):
    """Un seul fantôme ouvert par paire + sens + setup (et pas de doublon d'un trade réel ouvert)."""
    cle = lambda df: set(df["symbol"] + "|" + df["sens"] + "|" + df["setup"])
    ouverts = j[j["statut"].isin(["ATTENTE", "EN_COURS"])]
    recents = j[(j["type"] == "FANTOME") & (j["ts"] > (maintenant - DEDUP_HEURES * 3600) * 1000)]
    deja = cle(ouverts) | cle(recents)
    lignes = []
    for r in candidats:
        k = f"{r['symbol']}|{r['sens']}|{r['type']}"
        if k in deja: continue
        deja.add(k)
        statut = "EN_COURS" if (r["deja"] and r["dist"] <= DIST_TRADE_NOW) else "ATTENTE"
        lignes.append(ligne_journal(r, maintenant, "FANTOME", statut))
    return ajouter_lignes(j, lignes), len(lignes)

def parcours(row, bars, actif):
    """Rejoue un signal sur des bougies M15. Hypothèses prudentes : SL compté si TP et SL
    sont touchés dans la même bougie ; un fantôme n'est « entré » que si le prix touche l'entrée."""
    d = 1 if row["sens"] == "LONG" else -1
    e, sl, tp = float(row["entree"]), float(row["sl"]), float(row["tp"])
    risque = abs(e - sl)
    out = dict(statut=None, r=np.nan, t_sortie=None, mfe=0.0, mae=0.0,
               actif=actif, t_entree=float(row["ts"]) if actif else None)
    if risque <= 0:
        out["statut"] = "INVALIDE"; return out
    for _, b in bars.iterrows():
        fin = b.t + 900_000
        touche_sl = (b.l <= sl) if d == 1 else (b.h >= sl)
        touche_tp = (b.h >= tp) if d == 1 else (b.l <= tp)
        if not out["actif"]:
            if b.l <= e <= b.h:
                out["actif"], out["t_entree"] = True, b.t
            elif touche_sl:
                out.update(statut="INVALIDE", t_sortie=fin); return out
            elif touche_tp:
                out.update(statut="RATE", t_sortie=fin); return out
            else:
                continue
        if touche_sl:
            out.update(statut="SL", r=-1.0, t_sortie=fin, mae=1.0); return out
        fav = (b.h - e) if d == 1 else (e - b.l)
        adv = (e - b.l) if d == 1 else (b.h - e)
        out["mfe"] = max(out["mfe"], fav / risque)
        out["mae"] = max(out["mae"], adv / risque)
        if touche_tp:
            out.update(statut="TP", r=abs(tp - e) / risque, t_sortie=fin); return out
    return out

def fmt_date(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")

def evaluer_journal(j):
    """Met à jour tous les signaux ouverts (réels et fantômes). Une requête par paire."""
    msgs, n_clos = [], 0
    now_ms = time.time() * 1000
    expire_ms = JOURNAL_EXPIRE_H * 3_600_000
    ouverts = j[j["statut"].isin(["EN_COURS", "ATTENTE"])]
    for sym, groupe in ouverts.groupby("symbol"):
        m15 = klines(sym, "15", limit=KLINES_JOURNAL)
        time.sleep(0.15)
        if m15 is None: continue
        for i, row in groupe.iterrows():
            actif0 = pd.notna(row["ts_entree"]) and row["ts_entree"] == row["ts"]
            bars = m15[m15.t >= row["ts"]]
            p = parcours(row, bars, actif0)
            d = 1 if row["sens"] == "LONG" else -1
            risque = abs(row["entree"] - row["sl"])
            if p["statut"] is None:
                if p["actif"] and now_ms - p["t_entree"] > expire_ms and len(bars):
                    p.update(statut="EXPIRE", r=d * (bars.c.iloc[-1] - row["entree"]) / risque,
                             t_sortie=bars.t.iloc[-1] + 900_000)
                elif not p["actif"] and now_ms - row["ts"] > expire_ms:
                    p.update(statut="NON_DECLENCHE", t_sortie=now_ms)
                else:
                    j.loc[i, "statut"] = "EN_COURS" if p["actif"] else "ATTENTE"
                    if p["actif"]:
                        j.loc[i, "ts_entree"] = p["t_entree"]
                        j.loc[i, "mfe_R"] = round(p["mfe"], 2)
                        j.loc[i, "mae_R"] = round(p["mae"], 2)
                    continue
            statut = p["statut"]
            t_sortie = p["t_sortie"] if p["t_sortie"] is not None else now_ms
            j.loc[i, "statut"] = statut
            j.loc[i, "date_sortie"] = fmt_date(t_sortie)
            n_clos += 1
            if statut not in STATUTS_CLOS:
                continue
            r_mult = float(p["r"])
            frais = row["frais_R"] if pd.notna(row["frais_R"]) else 2 * FRAIS_TAKER * row["entree"] / risque
            t_e = p["t_entree"] if p["t_entree"] is not None else row["ts"]
            duree = (t_sortie - t_e) / 3_600_000
            j.loc[i, "ts_entree"] = t_e
            j.loc[i, "resultat_R"] = round(r_mult, 2)
            j.loc[i, "frais_R"] = round(frais, 2)
            j.loc[i, "resultat_net_R"] = round(r_mult - frais, 2)
            j.loc[i, "mfe_R"] = round(p["mfe"], 2)
            j.loc[i, "mae_R"] = round(p["mae"], 2)
            j.loc[i, "duree_h"] = round(duree, 1)
            if row["type"] == "REEL":
                icone = {"TP": "✅", "SL": "❌", "EXPIRE": "⌛"}[statut]
                libelle = {"TP": "TP touché", "SL": "SL touché", "EXPIRE": f"expiré après {JOURNAL_EXPIRE_H} h"}[statut]
                msgs.append(f"{icone} {row['symbol']} {row['sens']} (signal du {row['date_utc']} UTC, "
                            f"score {int(row['score'])}) — {libelle} : {r_mult:+.2f} R brut / "
                            f"{r_mult - frais:+.2f} R net en {duree:.1f} h (MFE {p['mfe']:+.2f} R)")
    return j, msgs, n_clos

def backfill_mfe(j):
    """Rattrape le MFE / MAE des anciens trades réels clôturés (quelques-uns par scan)."""
    m = (j["type"] == "REEL") & j["statut"].isin(STATUTS_CLOS) & j["mfe_R"].isna() & (j["backfill"] != "echec")
    n = 0
    for i, row in j[m].head(BACKFILL_MAX).iterrows():
        try:
            fin = datetime.strptime(row["date_sortie"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000
            bars = klines_periode(row["symbol"], row["ts"], fin)
        except Exception:
            bars = None
        time.sleep(0.15)
        if bars is None:
            j.loc[i, "backfill"] = "echec"; continue
        bars = bars[(bars.t >= row["ts"]) & (bars.t < fin)]
        p = parcours(row, bars, True)
        j.loc[i, "mfe_R"] = round(p["mfe"], 2)
        j.loc[i, "mae_R"] = round(p["mae"], 2)
        j.loc[i, "backfill"] = "ok"
        n += 1
    return j, n

# ---------------- SIMULATION CHRONOLOGIQUE DES SORTIES (V6.1) ----------------
def rejouer(row, bars, strat):
    """Rejoue un trade bougie M15 par bougie M15 avec une gestion de sortie donnée.
    Prudent : dans chaque bougie, le SL en place est testé AVANT tout le reste ;
    un déplacement de SL (BE, SL technique) ne s'applique qu'à partir de la bougie suivante.
    Sans sortie au bout de l'horizon : clôture au dernier cours. Résultat en R brut."""
    d = 1 if row["sens"] == "LONG" else -1
    e, sl, tp0 = float(row["entree"]), float(row["sl"]), float(row["tp"])
    R = abs(e - sl)
    if R <= 0 or not len(bars): return np.nan
    tp = e + d * 1.5 * R if strat == "sim_F" else e + d * 2 * R if strat == "sim_G" else tp0
    reste, gain, arme = 1.0, 0.0, False
    bas, hauts = [], []
    for _, b in bars.iterrows():
        if (d == 1 and b.l <= sl) or (d == -1 and b.h >= sl):
            return gain + reste * d * (sl - e) / R
        fav = ((b.h - e) if d == 1 else (e - b.l)) / R
        if strat == "sim_E" and reste == 1.0 and fav >= 1.0:
            gain, reste = 0.5, 0.5
        if (d == 1 and b.h >= tp) or (d == -1 and b.l <= tp):
            return gain + reste * abs(tp - e) / R
        bas.append(b.l); hauts.append(b.h)
        nouveau = None
        if strat == "sim_B" and fav >= 1.0: nouveau = e
        elif strat == "sim_C" and fav >= 1.5: nouveau = e
        elif strat == "sim_D":
            if fav >= 1.5: arme = True
            if arme: nouveau = min(bas[-TRAIL_N:]) if d == 1 else max(hauts[-TRAIL_N:])
        if nouveau is not None:
            sl = max(sl, nouveau) if d == 1 else min(sl, nouveau)
    return gain + reste * d * (bars.c.iloc[-1] - e) / R

def simuler_sorties(j):
    """Simule les 7 sorties pour chaque trade clôturé (réel ou fantôme) dont l'horizon
    de 48 h après l'entrée est écoulé. Quelques trades par scan."""
    now = time.time() * 1000
    H = JOURNAL_EXPIRE_H * 3_600_000
    m = j["statut"].isin(STATUTS_CLOS) & (j["sim_statut"] == "") & j["ts_entree"].notna() \
        & (now - j["ts_entree"] > H)
    n = 0
    for sym, g in j[m].head(SIM_MAX).groupby("symbol"):
        m15 = klines(sym, "15", limit=KLINES_JOURNAL)
        time.sleep(0.15)
        for i, row in g.iterrows():
            t0 = row["ts_entree"]; t1 = t0 + H
            bars = m15 if (m15 is not None and len(m15) and m15.t.iloc[0] <= t0) else None
            if bars is None:
                try: bars = klines_periode(sym, t0, t1)
                except Exception: bars = None
                time.sleep(0.15)
            if bars is not None:
                bars = bars[(bars.t >= t0) & (bars.t < t1)]
            if bars is None or not len(bars):
                j.loc[i, "sim_statut"] = "echec"; continue
            for c in SIM_COLS:
                j.loc[i, c] = round(rejouer(row, bars, c), 2)
            j.loc[i, "sim_statut"] = "ok"
            n += 1
    return j, n

# ---------------- STATISTIQUES ----------------
NUM_STATS = ["resultat_R", "resultat_net_R", "frais_R", "mfe_R", "mae_R", "rr", "score", "duree_h",
             "ecart_entree_R", "body_ratio", "wick_ratio", "close_pos", "vol_ratio", "dist_ATR",
             "touches_zone", "age_zone_h", "dernier_test_h", "largeur_zone_ATR"] + SIM_COLS

def _prep(df):
    df = df.copy()
    for c in NUM_STATS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["resultat_net_R"] = df["resultat_net_R"].fillna(df["resultat_R"] - df["frais_R"].fillna(0))
    df["tranche_score"] = pd.cut(df["score"], [-1, 79.5, 89.5, 100], labels=["<80", "80-89", "90-100"])
    df["btc_detail"] = df["btc_detail"].replace("", "n/d (avant V6)")
    df["rejet_confirme"] = df["rejet_confirme"].replace("", "n/d")
    return df

def _bloc_stats(df, titre, colonne, ordre=None):
    lignes = [f"\n### {titre}\n",
              "| | Trades | Gagnants | Taux | R moyen brut | R moyen net | R total net |",
              "|---|---|---|---|---|---|---|"]
    groupes = df.groupby(colonne, observed=True)
    cles = ordre if ordre else sorted(groupes.groups.keys(), key=str)
    for k in cles:
        if k not in groupes.groups: continue
        g = groupes.get_group(k)
        n = len(g); w = int((g["resultat_R"] > 0).sum())
        lignes.append(f"| {k} | {n} | {w} | {100*w/n:.0f} % | {g['resultat_R'].mean():+.2f} | "
                      f"{g['resultat_net_R'].mean():+.2f} | {g['resultat_net_R'].sum():+.2f} |")
    return "\n".join(lignes)

def _bloc_tranches(df, titre, colonne, bornes, libelles):
    d = df[df[colonne].notna()].copy()
    if not len(d): return ""
    d["_t"] = pd.cut(d[colonne], bornes, labels=libelles, right=False)
    return _bloc_stats(d, titre, "_t", libelles)

def _blocs_qualite(df):
    """Résultats selon la qualité de la zone H1 et de la bougie de déclenchement."""
    inf = float("inf")
    return [
        _bloc_stats(df, "Par rejet M15 confirmé", "rejet_confirme", ["oui", "non", "n/d"]),
        _bloc_tranches(df, "Par nombre de tests de la zone H1", "touches_zone",
                       [0, 2, 3, 4, inf], ["1", "2", "3", "≥4"]),
        _bloc_tranches(df, "Par âge de la zone (bougies H1)", "age_zone_h",
                       [0, 24, 72, inf], ["<24 h", "24-72 h", "≥72 h"]),
        _bloc_tranches(df, "Par ancienneté du dernier test (bougies H1)", "dernier_test_h",
                       [0, 12, 48, inf], ["<12 h", "12-48 h", "≥48 h"]),
        _bloc_tranches(df, "Par position de clôture M15 (sens du trade)", "close_pos",
                       [0, 0.6, 0.8, 1.01], ["<60 %", "60-80 %", "≥80 %"]),
        _bloc_tranches(df, "Par mèche de rejet M15", "wick_ratio",
                       [0, 0.2, 0.4, 1.01], ["<20 %", "20-40 %", "≥40 %"]),
        _bloc_tranches(df, "Par corps de bougie M15", "body_ratio",
                       [0, 0.3, 0.6, 1.01], ["<30 %", "30-60 %", "≥60 %"]),
        _bloc_tranches(df, "Par volume M15 (x moyenne 20)", "vol_ratio",
                       [0, 1, 1.5, inf], ["<1", "1-1,5", "≥1,5"]),
        _bloc_tranches(df, "Par distance à l'entrée (ATR H1)", "dist_ATR",
                       [0, 0.15, 0.35, inf], ["<0,15", "0,15-0,35", "≥0,35"]),
        _bloc_tranches(df, "Par largeur de zone (ATR H1)", "largeur_zone_ATR",
                       [0, 0.4, 0.8, inf], ["<0,4", "0,4-0,8", "≥0,8"])]

def _global(df):
    n = len(df); w = int((df["resultat_R"] > 0).sum())
    return "\n".join([
        f"- Taux de réussite : **{100*w/n:.0f} %** ({w}/{n})",
        f"- Espérance : **{df['resultat_R'].mean():+.2f} R brut** / **{df['resultat_net_R'].mean():+.2f} R net** par trade",
        f"- Frais moyens : {df['frais_R'].mean():.2f} R par trade",
        f"- Total : {df['resultat_R'].sum():+.2f} R brut / **{df['resultat_net_R'].sum():+.2f} R net** "
        f"(≈ {df['resultat_net_R'].sum()*RISQUE:+.2f} USDT avec {RISQUE} USDT de risque)",
        f"- Durée moyenne : {df['duree_h'].mean():.1f} h"])

def _bloc_mfe(df):
    d = df[df["mfe_R"].notna()]
    if not len(d):
        return "\n### MFE / MAE\nPas encore de données."
    lignes = ["\n### MFE / MAE (jusqu'où les trades sont allés)\n",
              f"- Trades mesurés : {len(d)} | RR visé moyen : {d['rr'].mean():.2f} | "
              f"MFE médian : **{d['mfe_R'].median():+.2f} R**",
              f"- Ont atteint +1 R : {100*(d['mfe_R'] >= 1).mean():.0f} % | +1,5 R : "
              f"{100*(d['mfe_R'] >= 1.5).mean():.0f} % | +2 R : {100*(d['mfe_R'] >= 2).mean():.0f} %"]
    p = d[d["statut"] == "SL"]
    if len(p):
        lignes.append(f"- **MFE des perdants** ({len(p)} SL) : avaient atteint +0,5 R : "
                      f"{100*(p['mfe_R'] >= 0.5).mean():.0f} % | +1 R : {100*(p['mfe_R'] >= 1).mean():.0f} % | "
                      f"+1,5 R : {100*(p['mfe_R'] >= 1.5).mean():.0f} % avant de toucher le SL")
    g = d[d["resultat_R"] > 0]
    if len(g):
        lignes.append(f"- **MAE des gagnants** ({len(g)}) : moyen -{g['mae_R'].mean():.2f} R | "
                      f"médian -{g['mae_R'].median():.2f} R | pire -{g['mae_R'].max():.2f} R "
                      f"| {100*(g['mae_R'] >= 0.5).mean():.0f} % sont descendus au-delà de -0,5 R")
    return "\n".join(lignes)

def _bloc_sorties(df, titre):
    """Comparaison des 7 gestions de sortie, rejouées bougie par bougie."""
    d = df[df["sim_statut"] == "ok"]
    if not len(d):
        return f"\n### {titre}\nPas encore de trade simulé (il faut 48 h après l'entrée)."
    lignes = [f"\n### {titre} — {len(d)} trades rejoués bougie par bougie\n",
              "| Gestion | Taux | R moyen brut | R moyen net | R total net |", "|---|---|---|---|---|"]
    for c, nom in STRATEGIES.items():
        s = d[c]; net = s - d["frais_R"].fillna(0)
        lignes.append(f"| {nom} | {100*(s > 0).mean():.0f} % | {s.mean():+.2f} | {net.mean():+.2f} | {net.sum():+.2f} |")
    lignes.append("\n_Prudent : SL testé avant le TP dans chaque bougie ; BE / SL technique actifs "
                  f"à partir de la bougie suivante ; horizon {JOURNAL_EXPIRE_H} h. "
                  "La ligne A peut différer légèrement du résultat réel (horizon fixe)._")
    return "\n".join(lignes)

def _avertissement(n):
    return f"\n⚠️ Seulement {n} trades clôturés : trop peu pour conclure (vise au moins 30 à 50 par catégorie)." if n < 30 else ""

def ecrire_stats(j):
    reel = j[j["type"] == "REEL"]
    fant_all = j[j["type"] == "FANTOME"]
    cur = reel[reel["version"] == VERSION_LOGIQUE]
    clos = _prep(cur[cur["statut"].isin(STATUTS_CLOS)])
    n_ouverts = int(j["statut"].isin(["EN_COURS", "ATTENTE"]).sum())
    n_attente_sim = int((j["statut"].isin(STATUTS_CLOS) & (j["sim_statut"] == "")).sum())
    out = [f"# 📒 Journal Trio Alt V{VERSION} (statistiques de la logique V{VERSION_LOGIQUE})\n",
           f"_Mis à jour le {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {len(j)} lignes dans le journal, "
           f"{n_ouverts} signaux ouverts, {n_attente_sim} trades clôturés en attente de simulation (48 h)._\n",
           f"Signaux réels V{VERSION_LOGIQUE} : **{len(cur)}** — clôturés : **{len(clos)}** — "
           f"en cours : **{int((cur['statut'] == 'EN_COURS').sum())}**"
           + (" — SHORT suivis en fantôme uniquement" if SHORT_MODE == "FANTOME" else "") + "\n",
           "_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés "
           f"dans la même bougie M15 ; clôture au prix du moment après {JOURNAL_EXPIRE_H} h. "
           "1 R = distance entrée–SL. R brut = hors frais ; R net = frais taker aller-retour déduits._\n"]

    out.append(f"\n## Trades réels V{VERSION_LOGIQUE}\n")
    if len(clos):
        out.append(_global(clos))
        out.append(_bloc_stats(clos, "Par setup", "setup"))
        out.append(_bloc_stats(clos, "Par sens", "sens", ["LONG", "SHORT"]))
        out.append(_bloc_stats(clos, "Par contexte BTC détaillé (H4-H1)", "btc_detail"))
        out.append(_bloc_stats(clos, "Par tranche de score", "tranche_score", ["<80", "80-89", "90-100"]))
        out += _blocs_qualite(clos)
        out.append(_bloc_mfe(clos))
        out.append(_bloc_sorties(clos, f"Sorties — trades réels V{VERSION_LOGIQUE}"))
        ec = clos["ecart_entree_R"].dropna()
        if len(ec):
            out.append(f"\n- Écart moyen entrée réelle (prix au signal) vs entrée théorique : {ec.mean():+.2f} R "
                       "(positif = entrée réelle moins favorable)")
        out.append(_avertissement(len(clos)))
    else:
        out.append(f"Aucun trade V{VERSION_LOGIQUE} clôturé pour l'instant.")

    fant = fant_all[fant_all["version"] == VERSION_LOGIQUE]
    if len(clos):
        d = clos.copy()
        d["ma_decision"] = d["ma_decision"].replace("", "sans réponse")
        out.append(f"\n## Mes décisions (alertes V{VERSION_LOGIQUE} clôturées)\n")
        out.append("_« pris » = tes trades. Compare-les à « pas pris » et à l'ensemble ci-dessus : "
                   "si « pris » fait mieux, ton tri apporte quelque chose._")
        out.append(_bloc_stats(d, "Résultat selon ta décision", "ma_decision", ["pris", "pas pris", "sans réponse"]))
        p = d[d["ma_decision"] == "pris"]
        if len(p):
            out.append(_bloc_stats(p, "Tes trades pris, selon BTC H4", "btc_h4"))
            out.append(_avertissement(len(p)))
    out.append(f"\n## Signaux fantômes V{VERSION_LOGIQUE} (non tradés : SHORT, WAIT, PREPARE)\n")
    if len(fant):
        cpt = fant["statut"].value_counts()
        out.append("Statuts : " + " | ".join(f"{k} {v}" for k, v in cpt.items()) + "\n")
        fc = _prep(fant[fant["statut"].isin(STATUTS_CLOS)])
        if len(fc):
            out.append(_global(fc))
            out.append(_bloc_stats(fc, "Fantômes par sens", "sens", ["LONG", "SHORT"]))
            out.append(_bloc_stats(fc, "Fantômes par raison de non-trade", "raison"))
            out.append(_bloc_stats(fc, "Fantômes par setup", "setup"))
            out.append(_bloc_stats(fc, "Fantômes par contexte BTC détaillé (H4-H1)", "btc_detail"))
            out += _blocs_qualite(fc)
            out.append(_bloc_mfe(fc))
            out.append(_bloc_sorties(fc, f"Sorties — fantômes V{VERSION_LOGIQUE}"))
            out.append(_avertissement(len(fc)))
    else:
        out.append("Aucun pour l'instant.")

    # Gestion de sortie : le comportement du prix après l'entrée ne dépend pas de la version
    # -> on rejoue tout ce qui est disponible (réels toutes versions + fantômes).
    tout = _prep(pd.concat([reel, fant_all])[lambda x: x["statut"].isin(STATUTS_CLOS)]) \
        if len(reel) + len(fant_all) else pd.DataFrame()
    if len(tout):
        out.append("\n## Gestion de sortie — tous les trades rejoués (réels toutes versions + fantômes)\n")
        out.append(_bloc_mfe(tout))
        out.append(_bloc_sorties(tout, "Sorties — ensemble"))

    # Vue cumulée de toutes les sous-versions 6.x (la V6.3 seule reste détaillée plus haut)
    v6 = reel[reel["version"].astype(str).str.startswith("6.")]
    clos6 = _prep(v6[v6["statut"].isin(STATUTS_CLOS)])
    if len(clos6):
        out.append("\n## Famille V6 (toutes sous-versions 6.x cumulées, trades réels)\n")
        out.append(_global(clos6))
        out.append(_bloc_stats(clos6, "Par sous-version", "version"))
        out.append(_bloc_stats(clos6, "Par sens", "sens", ["LONG", "SHORT"]))
        out.append(_bloc_mfe(clos6))
        out.append(_avertissement(len(clos6)))

    prec = _prep(reel[(reel["version"] != VERSION_LOGIQUE) & reel["statut"].isin(STATUTS_CLOS)])
    if len(prec):
        out.append("\n---\n\n## Versions précédentes (référence, non mélangé)\n")
        out.append(_bloc_stats(prec, "Trades réels par version", "version"))
        out.append(_bloc_stats(prec, "Par setup (toutes versions précédentes)", "setup"))
        out.append(_bloc_stats(prec, "Par sens (toutes versions précédentes)", "sens", ["LONG", "SHORT"]))
    with open(STATS, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

# ---------------- MAIN ----------------
def scan():
    print(f"TRIO ALT V{VERSION} — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    choisir_source_oi()
    df, info = tickers(), instruments()
    n0 = len(df)
    liq = df[(df.turnover24h >= MIN_TURNOVER) & (df.spread <= MAX_SPREAD)]
    liq = liq.sort_values("turnover24h", ascending=False).head(SHORTLIST)
    print(f"{n0} paires USDT → {len(liq)} liquides analysées en H4/H1/M15…")

    contexte_btc()
    preparer_scan(list(liq.symbol))
    actifs = [n for n, on in (("pullback", SETUP_PULLBACK), ("cassure + retest", SETUP_CASSURE),
                              ("range", SETUP_RANGE)) if on]
    print(f"Setups actifs : {', '.join(actifs)}")

    results = []                       # V6.1 : tous les setups de toutes les paires
    for i, (_, row) in enumerate(liq.iterrows(), 1):
        try:
            results.extend(analyse(row, info.get(row.symbol, {})))
        except Exception as ex:
            print(f"  {row.symbol} : erreur {ex}")
        if i % 20 == 0: print(f"  {i}/{len(liq)}…")
        time.sleep(0.15)

    src = OI_SOURCE[0] if OI_SOURCE else "aucune source"
    print(f"OI récupéré via {src} : {OI_STATS['ok']} paires OK / {OI_STATS['ko']} n/d")

    btc_sans_dir = BTC_FILTRE and BTC_CTX is not None and BTC_CTX["n_neutre"] == 2
    score_min = SCORE_MIN_BTC_NEUTRE if btc_sans_dir else SCORE_MIN
    max_now   = MAX_NOW_BTC_NEUTRE if btc_sans_dir else MAX_TRADE_NOW

    # V6.1 : SHORT en mode fantôme -> jamais tradés, suivis dans le journal
    def tradable(r): return not (SHORT_MODE == "FANTOME" and r["sens"] == "SHORT")

    # V6.1 : un setup par paire, choisi par priorité de décision puis proximité de l'entrée
    cle_prio = lambda r: (PRIO[r["decision"]], r["dist"])
    meilleurs = {}
    for r in results:
        if not tradable(r): continue
        b = meilleurs.get(r["symbol"])
        if b is None or cle_prio(r) < cle_prio(b): meilleurs[r["symbol"]] = r
    tri = (lambda r: -r["score"]) if TRI_PAR_SCORE else cle_prio
    ok = sorted([r for r in meilleurs.values() if r["decision"] != "NO TRADE"], key=tri)
    top = [r for r in ok if r["score"] >= score_min][:MAX_TOP]

    n_now = 0
    for r in top:
        if r["decision"] == "TRADE NOW":
            n_now += 1
            if n_now > max_now:
                r["decision"] = "WAIT"
                r["pourquoi"] = "plafond de TRADE NOW atteint (BTC sans direction) — un seul trade à la fois"

    pd.DataFrame([{k: v for k, v in r.items() if k not in ("inf", "sup", "res", "zone")}
                  for r in results]).to_csv(SCAN_CSV, index=False)

    alerte = ""   # V7.0 : le contexte BTC est dans la fiche de chaque alerte
    # V7.2 : résumé du scan (sans note) ; le détail des alertes envoyées est affiché plus bas
    def compte(decision, longs_seulement=True):
        return sum(1 for r in results if r["decision"] == decision
                   and (not longs_seulement or r["sens"] == "LONG"))
    print(f"\nSetups trouvés : {compte('TRADE NOW', False)} TRADE NOW · {compte('WAIT', False)} WAIT "
          f"(suivis en fantôme) · {compte('NO TRADE', False)} écartés")

    # Telegram — uniquement les TRADE NOW pas encore envoyés
    etat, maintenant = charger_etat(), time.time()
    nouveaux = [r for r in top if r["decision"] == "TRADE NOW"
                and maintenant - etat.get(cle_signal(r), 0) > DEDUP_HEURES * 3600]

    # Journal : suivi des signaux ouverts, rattrapage MFE, puis ajout des nouveaux
    journal = charger_journal()
    journal, notes = lire_decisions(journal)          # V7.1 : tes réponses « pris » / « non »
    for n in notes:
        print(n); telegram(n)
    journal, clotures, n_clos = evaluer_journal(journal)
    for m in clotures:
        print(m); telegram(m)
    journal, n_bf = backfill_mfe(journal)
    journal, n_sim = simuler_sorties(journal)
    journal = ajouter_reels(journal, nouveaux, maintenant)
    n_fant = 0
    if FANTOMES:
        exclus = {id(r) for r in top if r["decision"] == "TRADE NOW"}
        candidats = sorted([r for r in results if r["decision"] != "NO TRADE"
                            and r["score"] >= SCORE_MIN and id(r) not in exclus], key=cle_prio)
        journal, n_fant = ajouter_fantomes(journal, candidats, maintenant)
    journal.to_csv(JOURNAL, index=False)
    ecrire_stats(journal)
    print(f"Journal : {len(nouveaux)} réel(s) ajouté(s), {n_fant} fantôme(s) ajouté(s), "
          f"{n_clos} clôturé(s), MFE rattrapé sur {n_bf} ancien(s) trade(s), "
          f"sorties simulées sur {n_sim} trade(s), "
          f"{int((journal['statut'] == 'EN_COURS').sum())} en cours")

    for r in nouveaux:
        # V7.3 : 1) ticket copiable  2) fiche d'analyse (pourquoi TRADE NOW + lien)  3) ligne PEPITE
        telegram(ticket(r), html=True)
        telegram(fiche(r), html=True)
        telegram(ligne_pepite(r))
        etat[cle_signal(r)] = maintenant
    sauver_etat(etat)
    print(f"Telegram : {len(nouveaux)} nouvelle(s) alerte(s) TRADE NOW envoyée(s)")
    for r in nouveaux:                                  # V7.2 : la fiche, telle qu'envoyée
        print("\n" + unescape(re.sub(r"<[^>]+>", "", fiche(r))))
    if not nouveaux:
        print("Aucune nouvelle alerte ce scan. « Ne pas trader est aussi une décision de trading. »")

    n_prep = 0
    if PREPARE_ALERTE:
        prepares = [r for r in ok if r["decision"] == "PREPARE" and r["score"] >= PREPARE_SCORE_MIN
                    and maintenant - etat.get("PREPARE|" + cle_signal(r), 0) > DEDUP_HEURES * 3600]
        for r in prepares:
            entete = (f"🟡 CRYPTO PÉPITE — PREPARE (score {r['score']}) — {datetime.now(timezone.utc):%H:%M} UTC\n"
                      "Pas encore déclenché : ordre conditionnel possible, ou attendre le TRADE NOW.\n"
                      + resume_btc())
            if alerte: entete += "\n" + alerte
            telegram(entete + "\n" + rapport(r) + f"\n📈 Graphique TradingView (M15) : {lien_tv(r)}")
            telegram(ligne_pepite(r))
            etat["PREPARE|" + cle_signal(r)] = maintenant
            n_prep += 1
        sauver_etat(etat)
        print(f"Telegram : {n_prep} nouveau(x) PREPARE (score ≥ {PREPARE_SCORE_MIN}) envoyé(s)")

def main():
    try:
        scan()
    except BaseException as ex:
        if isinstance(ex, KeyboardInterrupt): raise
        msg = f"⚠️ TRIO ALT : le scan a échoué ({type(ex).__name__}) : {ex}"
        print(msg)
        telegram(msg)
        raise

if __name__ == "__main__":
    main()
