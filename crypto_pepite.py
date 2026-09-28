# ==============================================================================
#  CRYPTO PÉPITE V5.3 — Scanner intraday Zoomex Futures (USDT perpetuals)
#  Données : API publique Zoomex v3 (aucune clé API nécessaire)
#            + historique d'OI via la 1re source accessible parmi
#              Binance / OKX / Gate / Bybit (Zoomex n'a pas d'historique d'OI)
#  Couvre : liquidité, spread, H4/H1/M15, zones S/R, range, VWAP, RSI,
#           volume, OI (4h/24h), funding, RR, score, sizing 1 USDT.
#  + Filtre BTC : tendance H4/H1, choc 1h, corrélation alt/BTC.
#  NOUVEAU V4.4 : BTC neutre en H4 et/ou H1
#           -> alerte globale, malus pondéré par la corrélation,
#              malus renforcé sur les cassures,
#              et si H4 ET H1 neutres : score mini relevé + 1 seul TRADE NOW.
#  NOUVEAU V4.5 : envoi Telegram des NOUVEAUX TRADE NOW uniquement
#           (anti-doublon via etat_signaux.json) + alerte si le scan plante.
#           Lancement auto via cron-job.org -> GitHub Actions.
#  NOUVEAU V4.6 : tendance BTC (H4 / H1 / variation 1h) dans le message Telegram.
#  NOUVEAU V4.7 : lien TradingView + ligne PEPITE à coller dans l'indicateur Pine.
#  NOUVEAU V4.8 : journal des TRADE NOW (journal_signaux.csv) + suivi TP/SL automatique
#           + statistiques (journal_stats.md) + message Telegram à la clôture de chaque signal.
#  NOUVEAU V4.9 : alerte Telegram aussi pour les PREPARE à partir d'un score de 90.
#  NOUVEAU V5.0 : JAMAIS CONTRE BTC — tout setup LONG avec BTC baissier en H4 ou H1
#           (ou SHORT avec BTC haussier en H4 ou H1) est bloqué (NO TRADE).
#           Les TRADE NOW bloqués sont suivis en « fantômes » dans le journal
#           (colonne filtre) pour vérifier plus tard si le filtre a eu raison.
#  NOUVEAU V5.1 : diagnostic du journal — MFE / MAE, bougie ambiguë, TP touché après SL,
#           prix réel au signal, bougies chargées par période (plus de limite ~50 h),
#           rattrapage des anciens trades, simulation de TP fixe 1 / 1,5 / 2 R.
#  NOUVEAU V5.2 : détection des setups revue (nouveaux noms « (V5.2) » dans le journal)
#           - confirmation = vraie bougie de REJET M15 dans la zone (mèche, clôture, volume)
#             et entrée au prix réel (Market) -> sizing juste, plus de décalage entrée/prix
#           - cassure : on attend un VRAI retest (cassure venue d'en dessous, volume,
#             pas de réintégration, puis bougie de rejet sur la zone)
#           - zones filtrées : 2 à 6 tests + réaction passée d'au moins 1 ATR H1
#           - tendance H1 contre le trade = NO TRADE
#           - en attente de rejet = PREPARE (pas d'ordre conditionnel)
#           - TP sur la 1re zone adverse (plus de TP qui saute une résistance proche)
#           - anti-doublon basé sur le niveau de zone (le prix d'entrée bouge à chaque scan)
#  NOUVEAU V5.3 : univers élargi (120 paires, volume 24h >= 3 M USDT)
#           + alerte 🐜 PETITE PAIRE (volume 24h < 15 M USDT) dans le rapport et sur Telegram
#           + volume 24h enregistré dans le journal + statistiques « Par liquidité »
#  NE couvre PAS : news / macro -> à vérifier toi-même avant d'entrer.
# ==============================================================================
import os, json, time, math, requests
import numpy as np, pandas as pd
from datetime import datetime, timezone

# ---------------- PARAMÈTRES ----------------
BASE          = "https://openapi.zoomex.com"
CAPITAL       = 100.0        # USDT
RISQUE        = 1.0          # USDT max perdus au SL (frais inclus)
FRAIS_TAKER   = 0.0006       # 0,06 % par côté -> vérifie ton palier Zoomex
MIN_TURNOVER  = 3_000_000    # volume 24h minimum (USDT) — V5.3 : 5 M -> 3 M
MAX_SPREAD    = 0.0015       # 0,15 % max
MAX_MOVE_24H  = 0.15         # anti-FOMO : > 15 % sur 24h = mouvement passé
SHORTLIST     = 120          # nb de paires analysées en détail — V5.3 : 60 -> 120
MARGE_CIBLE   = 20.0         # marge max souhaitée par trade (USDT)
RR_MIN        = 1.5
SCORE_MIN     = 60
MAX_TOP       = 3            # nb max de setups affichés
MAX_TRADE_NOW = 3            # nb max de TRADE NOW en temps normal

# ---- Filtre BTC ----
BTC_FILTRE      = True
BTC_MALUS_FORT  = 15     # BTC contre le trade en H4 ET H1
BTC_MALUS_MOYEN = 7      # BTC contre le trade sur une seule UT
BTC_BONUS       = 5      # BTC dans le sens du trade en H4 ET H1
BTC_CHOC        = 0.012  # mouvement BTC sur 1h (M15) jugé violent : 1,2 %
CORR_FORTE      = 0.6    # corrélation H1 alt/BTC : effet plein au-dessus
CORR_FAIBLE     = 0.3    # effet réduit de moitié entre les deux, aucun effet en dessous
CORR_WAIT       = 0.5    # corrélation mini pour forcer un WAIT

# ---- NOUVEAU V4.4 : BTC neutre ----
BTC_NEUTRE_1UT        = 4    # malus si BTC neutre sur une seule UT (H4 ou H1)
BTC_NEUTRE_2UT        = 8    # malus si BTC neutre en H4 ET H1
BTC_NEUTRE_CASSURE    = 3    # malus en plus pour les setups de cassure
SCORE_MIN_BTC_NEUTRE  = 70   # score mini si BTC neutre en H4 ET H1
MAX_NOW_BTC_NEUTRE    = 1    # nb max de TRADE NOW si BTC neutre en H4 ET H1

# ---- NOUVEAU V4.5 : Telegram ----
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")    # secret GitHub (ou à remplir pour un test)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ETAT_FICHIER     = "etat_signaux.json"   # mémoire des signaux déjà envoyés
DEDUP_HEURES     = 6                     # un même signal n'est pas renvoyé avant 6 h

# ---- NOUVEAU V4.7 : TradingView ----
TV_PREFIXE = "ZOOMEX:"   # place de marché TradingView (ex. "BYBIT:" si Zoomex introuvable)
TV_SUFFIXE = ".P"        # suffixe des perpétuels sur TradingView

# ---- NOUVEAU V4.9 : alertes PREPARE ----
PREPARE_ALERTE    = True     # False pour couper les alertes PREPARE
PREPARE_SCORE_MIN = 90       # score mini pour recevoir un PREPARE sur Telegram

# ---- NOUVEAU V4.8 : journal ----
JOURNAL          = "journal_signaux.csv"
STATS            = "journal_stats.md"
JOURNAL_EXPIRE_H = 48        # un signal ni TP ni SL après 48 h est clôturé au prix du moment

# ---- NOUVEAU V5.0 : jamais contre BTC ----
BTC_JAMAIS_CONTRE = True     # False pour revenir au comportement V4.9
JOURNAL_FANTOMES  = True     # suit les TRADE NOW bloqués dans le journal (sans alerte Telegram)
FILTRE_CONTRE_BTC = "contre BTC"

# ---- NOUVEAU V5.2 : détection des setups ----
ZONE_TOUCHES_MIN = 2      # une zone doit avoir été testée au moins 2 fois
ZONE_TOUCHES_MAX = 6      # au-delà, la zone est usée et finit souvent par céder
REACTION_MIN_ATR = 1.0    # la zone a déjà fait repartir le prix d'au moins 1 ATR H1
REACTION_HORIZON = 12     # nb de bougies H1 pour mesurer cette réaction
REJET_MECHE      = 0.5    # mèche de rejet >= 50 % de la bougie M15
REJET_CLOTURE    = 0.6    # clôture dans les 40 % extrêmes du bon côté de la bougie
VOL_CONFIRM      = 1.0    # volume de la bougie de rejet >= moyenne des 20 dernières
VOL_CASSURE      = 1.2    # volume de la bougie de cassure >= 1,2 x la moyenne
CONFIRM_BARRES   = 2      # bougie de rejet cherchée dans les 2 dernières M15 clôturées
RETEST_FENETRE   = 12     # cassure cherchée dans les 12 dernières M15 (3 h)
AVANT_CASSURE    = 8      # le prix doit venir de l'autre côté de la zone dans les 8 M15 avant
RETEST_TOL       = 0.1    # tolérance de contact de la zone (en ATR H1)
SL_MARGE_ATR     = 0.25   # marge du SL au-delà de la zone / de la mèche (ATR H1)
DIST_MAX_NOW     = 0.25   # TRADE NOW si le prix est à moins de 0,25 ATR de la clôture de rejet
H1_ALIGNE        = True   # False pour ne plus bloquer les trades contre la tendance H1
TP_PREMIER_OBSTACLE = True  # TP sur la 1re zone adverse ; si elle est trop proche -> RR insuffisant

# ---- NOUVEAU V5.3 : petites paires ----
PETITE_PAIRE = 15_000_000   # en dessous de ce volume 24h (USDT) : alerte 🐜 PETITE PAIRE

NEUTRE = "NEUTRE/RANGE"

S = requests.Session()
OI_STATS = {"ok": 0, "ko": 0}
OI_SOURCE = None             # choisie automatiquement au démarrage
BTC_CTX   = None             # contexte BTC calculé une fois par scan
FANTOMES  = []               # V5.0 : setups bloqués par le filtre « jamais contre BTC »

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

def klines(sym, interval, limit=200):
    res = get("/cloud/trade/v3/market/kline", category="linear",
              symbol=sym, interval=interval, limit=limit)
    if not res or not res.get("list"):
        return None
    df = pd.DataFrame(res["list"]).iloc[:, :6]
    df.columns = ["t", "o", "h", "l", "c", "v"]
    df = df.astype(float).sort_values("t").reset_index(drop=True)
    return df.iloc[:-1].reset_index(drop=True)   # bougies CLÔTURÉES uniquement

# ---------------- OPEN INTEREST (multi-sources) ----------------
# Chaque fonction renvoie une liste de (timestamp_ms, oi) ou None.
def _oi_binance(sym):
    r = S.get("https://fapi.binance.com/futures/data/openInterestHist",
              params=dict(symbol=sym, period="1h", limit=25), timeout=15)
    if r.status_code != 200: return None
    d = r.json()
    if not isinstance(d, list): return None
    return [(int(x["timestamp"]), float(x["sumOpenInterest"])) for x in d]

def _oi_okx(sym):
    inst = sym[:-4] + "-USDT-SWAP"                        # BTCUSDT -> BTC-USDT-SWAP
    r = S.get("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",
              params=dict(instId=inst, period="1H", limit=25), timeout=15)
    if r.status_code != 200: return None
    j = r.json()
    if j.get("code") != "0": return None
    return [(int(x[0]), float(x[1])) for x in j.get("data", [])]

def _oi_gate(sym):
    c = sym[:-4] + "_USDT"                                # BTCUSDT -> BTC_USDT
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
    """Teste chaque source sur BTCUSDT et garde la première qui répond."""
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
    """Variation d'OI 4h / 24h (points horaires) depuis la source retenue."""
    if OI_SOURCE is None:
        OI_STATS["ko"] += 1
        return None, None
    for _ in range(2):
        try:
            pts = OI_SOURCE[1](sym)
        except Exception:
            time.sleep(0.5); continue
        if not pts or len(pts) < 25:
            break                                   # paire absente de la source
        pts.sort(key=lambda x: x[0], reverse=True)  # plus récent en premier
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
    V5.2 : chaque zone mesure aussi sa meilleure réaction passée (en ATR H1)."""
    d = df.tail(lookback).reset_index(drop=True)
    pts = []                                             # (prix, réaction en ATR)
    for i in range(k, len(d) - k):
        suite = d.iloc[i+1:i+1+REACTION_HORIZON]
        if d.h.iloc[i] == d.h.iloc[i-k:i+k+1].max():
            pts.append((d.h.iloc[i], (d.h.iloc[i] - suite.l.min()) / a))
        if d.l.iloc[i] == d.l.iloc[i-k:i+k+1].min():
            pts.append((d.l.iloc[i], (suite.h.max() - d.l.iloc[i]) / a))
    pts.sort(key=lambda x: x[0])
    clusters = []
    for p in pts:
        if clusters and p[0] - clusters[-1][-1][0] <= 0.5 * a: clusters[-1].append(p)
        else: clusters.append([p])
    out = []
    for c in clusters:
        prix = [p for p, _ in c]
        lo, hi = min(prix), max(prix)
        if hi - lo < 0.3 * a:
            m = (lo + hi) / 2; lo, hi = m - 0.15 * a, m + 0.15 * a
        out.append(dict(lo=lo, hi=hi, touches=len(c), reaction=max(r for _, r in c)))
    return out

def zone_ok(z):
    """V5.2 : zone assez testée, pas usée, et qui a déjà fait réagir le prix."""
    return ZONE_TOUCHES_MIN <= z["touches"] <= ZONE_TOUCHES_MAX and z["reaction"] >= REACTION_MIN_ATR

def vwap_jour(m15):
    d = m15.copy(); d["j"] = d.t // 86_400_000
    d = d[d.j == d.j.iloc[-1]]
    tp = (d.h + d.l + d.c) / 3
    return (tp * d.v).sum() / d.v.sum() if d.v.sum() > 0 else np.nan

# ---------------- FILTRE BTC ----------------
def contexte_btc():
    """Calcule une fois la tendance BTC H4/H1, le choc sur la dernière heure
    et (V4.4) le nombre d'UT où BTC est neutre."""
    global BTC_CTX
    h4, h1, m15 = klines("BTCUSDT", "240"), klines("BTCUSDT", "60"), klines("BTCUSDT", "15")
    if any(x is None or len(x) < 60 for x in (h4, h1, m15)):
        print("⚠️ Contexte BTC indisponible : filtre BTC désactivé pour ce scan")
        return
    choc = m15.c.iloc[-1] / m15.c.iloc[-5] - 1          # 4 bougies M15 clôturées = 1h
    t4, t1 = tendance(h4), tendance(h1)
    ut_neutres = [nom for nom, t in (("H4", t4), ("H1", t1)) if t == NEUTRE]
    BTC_CTX = dict(t4=t4, t1=t1, h1=h1, choc=choc,
                   n_neutre=len(ut_neutres), ut_neutres=ut_neutres)
    alerte = "  ⚡ CHOC" if abs(choc) >= BTC_CHOC else ""
    print(f"Contexte BTC : H4 {t4} | H1 {t1} | 1h {choc*100:+.2f} %{alerte}")

def alerte_btc_neutre():
    """Bandeau global quand BTC manque de direction (texte, ou '' si RAS)."""
    if not BTC_FILTRE or BTC_CTX is None or BTC_CTX["n_neutre"] == 0:
        return ""
    if BTC_CTX["n_neutre"] == 2:
        return ("⚠️ BTC SANS DIRECTION (H4 + H1 neutres) : marché indécis, faux départs fréquents.\n"
                f"   → Score mini relevé à {SCORE_MIN_BTC_NEUTRE}, {MAX_NOW_BTC_NEUTRE} seul TRADE NOW autorisé, "
                "cassures pénalisées. Privilégie les setups de range.")
    ut = BTC_CTX["ut_neutres"][0]
    return (f"⚠️ BTC neutre en {ut} : direction partielle, réduis l'exposition "
            f"(malus -{BTC_NEUTRE_1UT} pondéré par la corrélation).")

def resume_btc():
    """Ligne courte sur la tendance BTC pour le message Telegram."""
    if BTC_CTX is None:
        return "₿ BTC : tendance indisponible"
    fl = {"HAUSSIÈRE": "↗️", "BAISSIÈRE": "↘️", NEUTRE: "➡️"}
    t4, t1, choc = BTC_CTX["t4"], BTC_CTX["t1"], BTC_CTX["choc"]
    ligne = f"₿ BTC : H4 {t4} {fl.get(t4, '')} | H1 {t1} {fl.get(t1, '')} | 1h {choc*100:+.2f} %"
    if abs(choc) >= BTC_CHOC: ligne += " ⚡ CHOC"
    return ligne

def correlation_btc(h1):
    """Corrélation des rendements H1 alt/BTC sur les 48 dernières heures communes."""
    if BTC_CTX is None: return np.nan
    m = pd.merge(h1[["t", "c"]], BTC_CTX["h1"][["t", "c"]], on="t", suffixes=("", "_btc")).tail(49)
    if len(m) < 25: return np.nan
    return m.c.pct_change().corr(m.c_btc.pct_change())

def filtre_btc(sens, corr, setup_type=""):
    """Renvoie (points à ajouter au score, forcer WAIT ?, texte pour le rapport)."""
    if not BTC_FILTRE or BTC_CTX is None:
        return 0, False, "désactivé"
    contre = "BAISSIÈRE" if sens == "LONG" else "HAUSSIÈRE"
    pour   = "HAUSSIÈRE" if sens == "LONG" else "BAISSIÈRE"
    tfs = (BTC_CTX["t4"], BTC_CTX["t1"])
    n_contre, n_pour, n_neutre = tfs.count(contre), tfs.count(pour), tfs.count(NEUTRE)
    choc = BTC_CTX["choc"]
    choc_contre = (sens == "LONG" and choc <= -BTC_CHOC) or (sens == "SHORT" and choc >= BTC_CHOC)
    cassure = "Cassure" in setup_type

    c_ok = not pd.isna(corr)
    poids = 1.0 if (not c_ok or corr >= CORR_FORTE) else 0.5 if corr >= CORR_FAIBLE else 0.0

    # Direction BTC (inchangé V4.3)
    pts = -BTC_MALUS_FORT if n_contre == 2 else -BTC_MALUS_MOYEN if n_contre == 1 \
          else BTC_BONUS if n_pour == 2 else 0
    # V4.4 : BTC neutre
    pts_neutre = 0
    if n_neutre:
        pts_neutre = -(BTC_NEUTRE_2UT if n_neutre == 2 else BTC_NEUTRE_1UT)
        if cassure: pts_neutre -= BTC_NEUTRE_CASSURE
    pts = round((pts + pts_neutre) * poids)
    wait = (n_contre == 2 or choc_contre) and (not c_ok or corr >= CORR_WAIT)

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
    if poids == 0: etat += " — alt décorrélée, filtre sans effet"
    elif poids == 0.5: etat += " — corrélation moyenne, effet réduit"
    return pts, wait, f"{etat} | corrélation H1 {corr_txt} | impact score {pts:+d}"

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

def score(s, t4, t1, vol_ratio, oi4, ch4, rr, dist, row, r1):
    d = 1 if s["sens"] == "LONG" else -1
    want = "HAUSSIÈRE" if d == 1 else "BAISSIÈRE"
    sc = (15 if t4 == want else 7 if t4 == NEUTRE else 0)
    sc += (10 if t1 == want else 5 if t1 == NEUTRE else 0)
    sc += max(0, 20 * (1 - dist))                           # timing
    sc += max(0, min(15, 15 * (vol_ratio - 0.8) / 0.8))    # volume
    if oi4 is None: sc += 5
    else:
        p, o = ch4 * d > 0, oi4 > 0
        sc += 15 if (p and o) else 10 if (not p and not o) else 5 if p else 0
    sc += 15 if rr >= 2.5 else 12 if rr >= 2 else 8 if rr >= RR_MIN else 0
    to = row.turnover24h
    sc += 10 if to >= 50e6 else 7 if to >= 15e6 else 4
    if row.spread > 0.0008: sc -= 3
    if not pd.isna(row.fundingRate) and d * row.fundingRate > 0.0005: sc -= 10
    if (d == 1 and r1 > 75) or (d == -1 and r1 < 25): sc -= 10
    return int(max(0, min(100, round(sc))))

def arrondi(x, tick):
    return round(round(x / tick) * tick, 10) if tick else x

def sizing(e, sl, inf):
    dist = abs(e - sl)
    q = RISQUE / (dist + 2 * FRAIS_TAKER * e)             # frais inclus dans le 1 USDT
    step = inf.get("step")
    if step: q = math.floor(q / step) * step
    notional = q * e
    lev = max(1, math.ceil(notional / MARGE_CIBLE))
    return dict(q=q, notional=notional, lev=lev, marge=notional / lev,
                risque=q * dist + 2 * FRAIS_TAKER * notional,
                trop_petit=bool(inf.get("minq") and q < inf["minq"]))

# ---------------- DÉTECTION DES SETUPS (V5.2) ----------------
def bougie_rejet(b, sens, vol_moy):
    """Mèche de rejet du bon côté, clôture dans l'extrême, volume suffisant."""
    rng = b.h - b.l
    if rng <= 0: return None
    if sens == "LONG":
        meche, cloture = (min(b.o, b.c) - b.l) / rng, (b.c - b.l) / rng
    else:
        meche, cloture = (b.h - max(b.o, b.c)) / rng, (b.h - b.c) / rng
    vol = b.v / vol_moy if vol_moy > 0 else 0.0
    return dict(ok=meche >= REJET_MECHE and cloture >= REJET_CLOTURE and vol >= VOL_CONFIRM,
                meche=meche, vol=vol)

def chercher_rejet(m15, z, sens, a1, vol_moy, apres=None):
    """Bougie de rejet la plus récente sur la zone, parmi les CONFIRM_BARRES dernières M15.
    apres = index de la bougie de cassure (le retest doit venir après)."""
    n = len(m15)
    for k in range(1, CONFIRM_BARRES + 1):
        idx = n - k
        if apres is not None and idx <= apres: break
        b = m15.iloc[idx]
        if sens == "LONG":
            contact = z["lo"] - SL_MARGE_ATR * a1 <= b.l <= z["hi"] + RETEST_TOL * a1 and b.c > z["hi"]
        else:
            contact = z["lo"] - RETEST_TOL * a1 <= b.h <= z["hi"] + SL_MARGE_ATR * a1 and b.c < z["lo"]
        if not contact: continue
        rj = bougie_rejet(b, sens, vol_moy)
        if rj and rj["ok"]: return b, rj
    return None, None

def chercher_cassure(m15, z, sens, vol_moy):
    """Index de la cassure la plus récente (clôture M15 qui franchit la zone en venant
    de l'autre côté, avec volume), sans réintégration depuis. None sinon."""
    c, n = m15.c.values, len(m15)
    for i in range(n - 2, max(AVANT_CASSURE, n - 1 - RETEST_FENETRE), -1):
        avant = c[i - AVANT_CASSURE:i]
        if sens == "LONG":
            casse = c[i] > z["hi"] and c[i - 1] <= z["hi"] and (avant < z["lo"]).any()
            rate = (c[i + 1:] < z["lo"]).any()
        else:
            casse = c[i] < z["lo"] and c[i - 1] >= z["lo"] and (avant > z["hi"]).any()
            rate = (c[i + 1:] > z["hi"]).any()
        if casse:
            if rate or m15.v.iloc[i] < VOL_CASSURE * vol_moy: return None
            return i
    return None

def detecter(sens, z, m15, px, a1, vol_moy):
    """Construit le setup V5.2 sur la zone la plus proche (ou None)."""
    L = sens == "LONG"
    bord, oppose = (z["hi"], z["lo"]) if L else (z["lo"], z["hi"])
    marge = SL_MARGE_ATR * a1
    i_cass = chercher_cassure(m15, z, sens, vol_moy)
    if i_cass is not None:
        type_ = "Cassure + vrai retest M15 (V5.2)" if L else "Cassure baissière + vrai retest M15 (V5.2)"
        b, rj = chercher_rejet(m15, z, sens, a1, vol_moy, apres=i_cass)
        attente = "cassure validée, en attente du retest de la zone avec bougie de rejet M15"
    else:
        type_ = "Rebond support H1 + rejet M15 (V5.2)" if L else "Rejet résistance H1 + mèche M15 (V5.2)"
        b, rj = chercher_rejet(m15, z, sens, a1, vol_moy)
        attente = "en attente d'une bougie de rejet M15 sur la zone"
        proche = (z["lo"] <= px <= z["hi"] + 0.5 * a1) if L else (z["lo"] - 0.5 * a1 <= px <= z["hi"])
        if b is None and not proche: return None      # ni rejet, ni prix au contact de la zone
    base = dict(sens=sens, type=type_, dir="haut" if L else "bas", zone=z, niveau=bord)
    if b is not None:
        extreme = b.l if L else b.h
        sl = (min(extreme, oppose) - marge) if L else (max(extreme, oppose) + marge)
        heure = datetime.fromtimestamp(b.t / 1000, timezone.utc).strftime("%H:%M")
        return dict(base, entry=px, sl=sl, trig=b.c, deja=True, attente_rejet=False,
                    conf_txt=f"bougie de rejet M15 de {heure} UTC — mèche {rj['meche']*100:.0f} % "
                             f"de la bougie, volume x{rj['vol']:.2f}")
    sl = (oppose - marge) if L else (oppose + marge)
    return dict(base, entry=bord, sl=sl, trig=bord, deja=False, attente_rejet=True, conf_txt=attente)

# ---------------- ANALYSE D'UNE PAIRE ----------------
def analyse(row, inf):
    sym, px = row.symbol, row.lastPrice
    h4, h1, m15 = klines(sym, "240"), klines(sym, "60"), klines(sym, "15")
    if any(x is None or len(x) < 60 for x in (h4, h1, m15)): return None
    a1 = atr(h1).iloc[-1]
    t4, t1, t15 = tendance(h4), tendance(h1), tendance(m15)
    zs = zones(h1, a1)
    sup = sorted([z for z in zs if (z["lo"] + z["hi"]) / 2 < px], key=lambda z: -z["hi"])
    res = sorted([z for z in zs if (z["lo"] + z["hi"]) / 2 >= px], key=lambda z: z["lo"])
    vol_moy = m15.v.iloc[-21:-1].mean()
    vol_ratio = m15.v.iloc[-1] / vol_moy if vol_moy > 0 else 0.0
    r1 = rsi(h1.c).iloc[-1]
    oi4, oi24 = oi_change(sym)
    est_btc = sym == "BTCUSDT"
    corr = np.nan if est_btc else correlation_btc(h1)
    ch4 = h1.c.iloc[-1] / h1.c.iloc[-5] - 1        # 4h entre bougies clôturées, aligné sur l'OI horaire
    setups = []

    # V5.2 : seule la zone la plus proche de chaque côté, si elle est de qualité
    if sup and zone_ok(sup[0]):
        s = detecter("LONG", sup[0], m15, px, a1, vol_moy)
        if s: setups.append(s)
    if res and zone_ok(res[0]):
        s = detecter("SHORT", res[0], m15, px, a1, vol_moy)
        if s: setups.append(s)

    best = None
    for s in setups:
        e, sl = s["entry"], s["sl"]; rd = abs(e - sl)
        if rd <= 0: continue
        # V5.2 : le TP ne saute plus par-dessus une zone adverse proche
        if s["sens"] == "LONG":
            seuil = e if TP_PREMIER_OBSTACLE else e + rd
            tgt = next((z["lo"] for z in res if z["lo"] > seuil), None)
            tp = tgt if tgt else e + 2 * rd
        else:
            seuil = e if TP_PREMIER_OBSTACLE else e - rd
            tgt = next((z["hi"] for z in sup if z["hi"] < seuil), None)
            tp = tgt if tgt else e - 2 * rd
        rr = abs(tp - e) / rd
        dist = abs(px - s["trig"]) / a1                  # V5.2 : distance au déclencheur
        contre = (s["sens"] == "LONG" and t4 == "BAISSIÈRE") or (s["sens"] == "SHORT" and t4 == "HAUSSIÈRE")
        contre_h1 = H1_ALIGNE and ((s["sens"] == "LONG" and t1 == "BAISSIÈRE") or
                                   (s["sens"] == "SHORT" and t1 == "HAUSSIÈRE"))
        bf = (0, False, "sans objet (BTC lui-même)") if est_btc else filtre_btc(s["sens"], corr, s["type"])
        if rr < RR_MIN: dec, why = "NO TRADE", f"RR insuffisant ({rr:.2f})"
        elif abs(row.price24hPcnt) > MAX_MOVE_24H: dec, why = "NO TRADE", "mouvement 24h déjà fait"
        elif dist > 1.0: dec, why = "NO TRADE", "prix trop loin de l'entrée (trop tard)"
        elif contre_h1: dec, why = "NO TRADE", "tendance H1 contre le trade"
        elif contre: dec, why = "WAIT", "contre-tendance H4"
        elif bf[1]: dec, why = "WAIT", "BTC contre le trade (attendre que BTC se stabilise)"
        elif s["deja"] and dist <= DIST_MAX_NOW: dec, why = "TRADE NOW", "bougie de rejet confirmée, prix proche"
        elif s["deja"]: dec, why = "NO TRADE", "rejet confirmé mais prix déjà parti (trop tard)"
        else: dec, why = "PREPARE", s["conf_txt"]
        # V5.0 : jamais contre BTC (BTC contre le sens en H4 OU en H1)
        dec_brute = dec
        bloque = BTC_JAMAIS_CONTRE and contexte_btc_label(s["sens"]) == "contre"
        if bloque:
            dec, why = "NO TRADE", f"contre BTC — bloqué par le filtre V5.0 (sinon : {dec_brute})"
        sc = score(s, t4, t1, vol_ratio, oi4, ch4, rr, dist, row, r1)
        sc = int(max(0, min(100, sc + bf[0])))
        cand = dict(s, symbol=sym, px=px, tp=tp, tp_theorique=tgt is None, rr=rr, dist=dist,
                    decision=dec, pourquoi=why, score=sc, t4=t4, t1=t1, t15=t15,
                    sup=sup[:2], res=res[:2], vol_ratio=vol_ratio, oi4=oi4, oi24=oi24,
                    ch4=ch4, funding=row.fundingRate, rsi_h1=r1, vwap=vwap_jour(m15),
                    atr_h1=a1, turnover=row.turnover24h, spread=row.spread,
                    ch24=row.price24hPcnt, inf=inf,
                    corr_btc=corr, btc_pts=bf[0], btc_txt=bf[2],
                    bloque_btc=bloque, decision_brute=dec_brute)
        if bloque: FANTOMES.append(cand)
        # V5.0 : un setup autorisé passe devant un setup bloqué, puis le meilleur score
        if best is None or (cand["bloque_btc"], -cand["score"]) < (best["bloque_btc"], -best["score"]):
            best = cand
    return best

# ---------------- RAPPORT ----------------
def alerte_petite_paire(c):
    """V5.3 : texte d'alerte si le volume 24h est faible, sinon ''."""
    if c["turnover"] >= PETITE_PAIRE: return ""
    return (f"🐜 PETITE PAIRE (volume 24h {c['turnover']/1e6:.1f} M USDT < {PETITE_PAIRE/1e6:.0f} M) : "
            "fausses mèches plus fréquentes, supports/résistances moins fiables, OI souvent n/d. "
            "Vérifie le graphique avant d'entrer.")

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
    if c["decision"] == "TRADE NOW":
        ordre = "Market (entrée au prix actuel)"
    elif c.get("attente_rejet"):
        ordre = "Aucun pour l'instant — attendre la bougie de rejet M15 (alerte TRADE NOW)"
    else:
        ordre = "Conditional (déclenchement au niveau d'entrée)"
    z = c["zone"]
    petite = alerte_petite_paire(c)
    petite = f"{petite}\n" if petite else ""
    return f"""
══════════════════════════════════════════════
{c['symbol']}  |  Prix {c['px']}  |  Score {c['score']}/100  |  {c['decision']}
══════════════════════════════════════════════
{petite}Tendance H4 : {c['t4']} | H1 : {c['t1']} | M15 : {c['t15']}
Supports    : {' | '.join(fz(z, t) for z in c['sup']) or 'aucun identifié'}
Résistances : {' | '.join(fz(z, t) for z in c['res']) or 'aucune identifiée'}{rng}
VWAP jour : {arrondi(c['vwap'], t)} | RSI H1 : {c['rsi_h1']:.0f} | ATR H1 : {c['atr_h1']:.6g}
Volume M15 : x{c['vol_ratio']:.2f} la moyenne 20 | Volume 24h : {c['turnover']/1e6:.1f} M USDT | Variation 24h : {c['ch24']*100:+.1f} %
OI ({src}) : {oi_txt} | Funding Zoomex : {c['funding']*100:.4f} %
→ {interp_oi(c['ch4'], c['oi4'])} ; {interp_funding(c['funding'])}
Filtre BTC : {c['btc_txt']}

Sens : {c['sens']} | Setup : {c['type']}
Zone : {fz(z, t)} | réaction passée {z['reaction']:.1f} ATR H1
Confirmation : {c['conf_txt']}
Ordre Zoomex : {ordre}
Entrée : {e}{' (estimée, bord de zone)' if c.get('attente_rejet') else ''} | SL : {sl} | TP : {tp}{' (théorique 2R, pas de zone identifiée)' if c['tp_theorique'] else ''}
RR : {c['rr']:.2f}
Capital : {CAPITAL:.0f} USDT | Risque visé : {RISQUE} USDT (frais inclus)
Quantité : {sz['q']:.6g} tokens | Notionnel : {sz['notional']:.2f} USDT
Levier : x{sz['lev']} | Marge ≈ {sz['marge']:.2f} USDT | Risque réel au SL ≈ {sz['risque']:.2f} USDT{'  ⚠️ quantité < minimum Zoomex' if sz['trop_petit'] else ''}
Alerte TradingView : M15 — prix touche la zone {arrondi(z['lo'], t)} – {arrondi(z['hi'], t)}, puis attendre la bougie de rejet
Invalidation : clôture H1 {'sous' if c['sens']=='LONG' else 'au-dessus de'} {sl}
Pourquoi maintenant : {c['pourquoi']} ; distance au déclencheur = {c['dist']:.2f} ATR H1
⚠️ News / macro NON vérifiées par le script : contrôle avant d'entrer."""

# ---------------- TELEGRAM ----------------
def telegram(texte):
    """Envoie un message (découpé si > 4000 caractères). Sans token : affichage seul."""
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
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              data=dict(chat_id=TELEGRAM_CHAT_ID, text=m,
                                        disable_web_page_preview=True), timeout=15)
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
    limite = time.time() - 24 * 3600                        # on oublie ce qui a plus de 24 h
    etat = {k: v for k, v in etat.items() if v >= limite}
    with open(ETAT_FICHIER, "w", encoding="utf-8") as f: json.dump(etat, f)

def lien_tv(r):
    return f"https://www.tradingview.com/chart/?symbol={TV_PREFIXE}{r['symbol']}{TV_SUFFIXE}&interval=15"

def ligne_pepite(r):
    """Ligne à coller dans l'indicateur TradingView « Crypto Pépite »."""
    t = r["inf"].get("tick")
    return f"PEPITE;{r['symbol']};{r['sens']};{arrondi(r['entry'], t)};{arrondi(r['sl'], t)};{arrondi(r['tp'], t)}"

def cle_signal(r):
    """Même paire + même sens + même setup + même niveau de zone = même signal.
    V5.2 : le niveau de zone remplace le prix d'entrée, qui bouge à chaque scan."""
    t = r["inf"].get("tick")
    return f"{r['symbol']}|{r['sens']}|{r['type']}|{arrondi(r.get('niveau', r['entry']), t)}"

# ---------------- JOURNAL (V5.1) ----------------
# NOUVEAU V5.1 :
#   - mfe_R  : meilleur mouvement en ta faveur avant la sortie (en R)
#   - mae_R  : pire mouvement contre toi avant la sortie (en R, -1 = SL)
#   - ambigu : OUI si TP et SL touchés dans la même bougie M15 (compté SL)
#   - tp_apres_sl : OUI si le TP a été touché APRÈS le SL, dans les 48 h du signal
#   - px_signal : prix réel au moment du signal (l'ordre TRADE NOW part au Market)
#   - bougies récupérées par période (start/end) : plus de limite à ~50 h
#   - rattrapage automatique des anciens trades clôturés au 1er lancement
#   - section « Diagnostic » + simulation de TP fixe à 1 / 1,5 / 2 R dans journal_stats.md
COLS_JOURNAL = ["id", "date_utc", "ts", "symbol", "sens", "setup", "score", "entree", "px_signal",
                "sl", "tp", "rr", "btc_h4", "btc_h1", "btc_ctx", "corr_btc", "btc_pts",
                "statut", "date_sortie", "resultat_R", "duree_h", "filtre",
                "mfe_R", "mae_R", "ambigu", "tp_apres_sl", "volume_24h_M"]
CLOS = ["TP", "SL", "EXPIRE"]

def charger_journal():
    try:
        j = pd.read_csv(JOURNAL)
        for c in COLS_JOURNAL:
            if c not in j: j[c] = np.nan
        j["statut"] = j["statut"].astype(str)
        j["date_sortie"] = j["date_sortie"].astype(object)
        for c in ("filtre", "ambigu", "tp_apres_sl"):               # "" = pas encore renseigné
            j[c] = j[c].fillna("").astype(str).replace("nan", "")
        for c in ("mfe_R", "mae_R", "px_signal", "volume_24h_M"):
            j[c] = pd.to_numeric(j[c], errors="coerce")
        return j[COLS_JOURNAL]
    except Exception:
        return pd.DataFrame(columns=COLS_JOURNAL)

def contexte_btc_label(sens):
    """Résumé simple du contexte BTC au moment du signal : sens / contre / neutre."""
    if BTC_CTX is None: return "n/d"
    pour = "HAUSSIÈRE" if sens == "LONG" else "BAISSIÈRE"
    contre = "BAISSIÈRE" if sens == "LONG" else "HAUSSIÈRE"
    tfs = (BTC_CTX["t4"], BTC_CTX["t1"])
    if contre in tfs: return "contre"
    if pour in tfs: return "sens"
    return "neutre"

def ajouter_au_journal(j, signaux, maintenant, filtre=""):
    lignes = []
    for r in signaux:
        t = r["inf"].get("tick")
        e, sl, tp = arrondi(r["entry"], t), arrondi(r["sl"], t), arrondi(r["tp"], t)
        lignes.append(dict(
            id=cle_signal(r), date_utc=datetime.fromtimestamp(maintenant, timezone.utc).strftime("%Y-%m-%d %H:%M"),
            ts=int(maintenant * 1000), symbol=r["symbol"], sens=r["sens"], setup=r["type"],
            score=r["score"], entree=e, px_signal=r["px"], sl=sl, tp=tp, rr=round(r["rr"], 2),
            btc_h4=BTC_CTX["t4"] if BTC_CTX else "", btc_h1=BTC_CTX["t1"] if BTC_CTX else "",
            btc_ctx=contexte_btc_label(r["sens"]),
            corr_btc=None if pd.isna(r["corr_btc"]) else round(float(r["corr_btc"]), 2),
            btc_pts=r["btc_pts"], statut="EN_COURS", date_sortie="", resultat_R=np.nan, duree_h=np.nan,
            filtre=filtre, mfe_R=np.nan, mae_R=np.nan, ambigu="", tp_apres_sl="",
            volume_24h_M=round(float(r["turnover"]) / 1e6, 1)))
    if lignes:
        j = pd.concat([j, pd.DataFrame(lignes, columns=COLS_JOURNAL)], ignore_index=True)
    return j

def klines_periode(sym, debut_ms, fin_ms):
    """Bougies M15 CLÔTURÉES entre debut_ms et fin_ms, par paquets de 200."""
    maintenant = time.time() * 1000
    fin_ms = min(fin_ms, maintenant)
    t0 = int(debut_ms // 900_000 * 900_000)
    morceaux = []
    while t0 < fin_ms:
        t1 = int(min(fin_ms, t0 + 199 * 900_000))
        res = get("/cloud/trade/v3/market/kline", category="linear", symbol=sym,
                  interval="15", start=t0, end=t1, limit=200)
        time.sleep(0.15)
        if not res or not res.get("list"): break
        df = pd.DataFrame(res["list"]).iloc[:, :6]
        df.columns = ["t", "o", "h", "l", "c", "v"]
        morceaux.append(df.astype(float))
        t0 = t1 + 900_000
    if not morceaux: return None
    df = pd.concat(morceaux).drop_duplicates("t").sort_values("t")
    return df[df.t + 900_000 <= maintenant].reset_index(drop=True)

def parcourir(row, bars):
    """Rejoue les bougies M15 du signal. Le MFE s'arrête AVANT la bougie du SL
    (on ne sait pas si le haut de cette bougie est venu avant ou après le SL)."""
    d = 1 if row.sens == "LONG" else -1
    risque = abs(row.entree - row.sl)
    mfe = mae = 0.0
    for _, b in bars.iterrows():
        touche_sl = (b.l <= row.sl) if d == 1 else (b.h >= row.sl)
        touche_tp = (b.h >= row.tp) if d == 1 else (b.l <= row.tp)
        if touche_sl:
            return dict(statut="SL", r=-1.0, t=b.t + 900_000, mfe=mfe, mae=-1.0, ambigu=bool(touche_tp))
        fav = (b.h - row.entree) if d == 1 else (row.entree - b.l)
        adv = (b.l - row.entree) if d == 1 else (row.entree - b.h)
        mfe, mae = max(mfe, fav / risque), min(mae, adv / risque)
        if touche_tp:
            return dict(statut="TP", r=abs(row.tp - row.entree) / risque, t=b.t + 900_000,
                        mfe=mfe, mae=mae, ambigu=False)
    return dict(statut=None, mfe=mfe, mae=mae, ambigu=False)

def _ms(date_txt):
    return int(pd.Timestamp(date_txt, tz="UTC").value // 1_000_000)

def evaluer_journal(j):
    """Suit les signaux EN_COURS (TP / SL / expiration), calcule MFE / MAE / ambiguïté,
    rattrape les anciens trades clôturés, et vérifie si le TP a été touché après un SL."""
    msgs = []
    maintenant = time.time() * 1000
    duree_max = JOURNAL_EXPIRE_H * 3_600_000
    a_voir = (j.statut == "EN_COURS") | (j.statut.isin(CLOS) & (j.ambigu == "")) | \
             ((j.statut == "SL") & (j.tp_apres_sl == ""))
    for i, row in j[a_voir].iterrows():
        if abs(row.entree - row.sl) <= 0: continue
        fin = row.ts + duree_max
        bars = klines_periode(row.symbol, row.ts, fin)
        if bars is None:                                   # repli : 200 dernières bougies
            bars = klines(row.symbol, "15")
        if bars is None: continue
        bars = bars[(bars.t >= row.ts) & (bars.t < fin)].reset_index(drop=True)
        complet = len(bars) > 0 and bars.t.iloc[0] <= row.ts + 2 * 900_000
        d = 1 if row.sens == "LONG" else -1
        p = parcourir(row, bars)
        statut, t_sortie = row.statut, None

        # 1) Signal en cours : clôture éventuelle
        if statut == "EN_COURS":
            if p["statut"] is None and len(bars) and maintenant >= fin:
                p.update(statut="EXPIRE", r=d * (bars.c.iloc[-1] - row.entree) / abs(row.entree - row.sl),
                         t=bars.t.iloc[-1] + 900_000)
            if p["statut"] is None: continue
            statut, r_mult, t_sortie = p["statut"], p["r"], p["t"]
            duree = (t_sortie - row.ts) / 3_600_000
            j.loc[i, "statut"] = statut
            j.loc[i, "resultat_R"] = round(r_mult, 2)
            j.loc[i, "duree_h"] = round(duree, 1)
            j.loc[i, "date_sortie"] = datetime.fromtimestamp(t_sortie / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
            j.loc[i, "mfe_R"], j.loc[i, "mae_R"] = round(p["mfe"], 2), round(p["mae"], 2)
            j.loc[i, "ambigu"] = "OUI" if p["ambigu"] else "NON"
            icone = {"TP": "✅", "SL": "❌", "EXPIRE": "⌛"}[statut]
            libelle = {"TP": "TP touché", "SL": "SL touché" + (" (bougie ambiguë)" if p["ambigu"] else ""),
                       "EXPIRE": f"expiré après {JOURNAL_EXPIRE_H} h"}[statut]
            fantome = "👻 [FILTRÉ, non tradé] " if str(row.filtre) not in ("", "nan") else ""
            msgs.append(f"{fantome}{icone} {row.symbol} {row.sens} (signal du {row.date_utc} UTC, score {int(row.score)}) — "
                        f"{libelle} : {r_mult:+.2f} R en {duree:.1f} h | meilleur moment {p['mfe']:+.2f} R")

        # 2) Ancien trade clôturé sans MFE : rattrapage si l'historique est complet et cohérent
        elif row.ambigu == "":
            if not complet:
                if maintenant - row.ts > 30 * 86_400_000: j.loc[i, "ambigu"] = "n/d"   # abandon après 30 j
            elif p["statut"] == statut or (p["statut"] is None and statut == "EXPIRE"):
                j.loc[i, "mfe_R"], j.loc[i, "mae_R"] = round(p["mfe"], 2), round(p["mae"], 2)
                j.loc[i, "ambigu"] = "OUI" if p["ambigu"] else "NON"
            else:
                j.loc[i, "ambigu"] = "n/d"                 # ancien résultat incohérent : on n'invente rien

        # 3) Après un SL : le TP a-t-il été touché ensuite (dans les 48 h du signal) ?
        if statut == "SL" and j.loc[i, "tp_apres_sl"] == "":
            if t_sortie is None:
                try: t_sortie = _ms(row.date_sortie)
                except Exception: continue
            apres = bars[bars.t >= t_sortie]
            touche = ((apres.h >= row.tp) if d == 1 else (apres.l <= row.tp)).any()
            if touche: j.loc[i, "tp_apres_sl"] = "OUI"
            elif maintenant >= fin and complet: j.loc[i, "tp_apres_sl"] = "NON"
            elif maintenant - row.ts > 30 * 86_400_000: j.loc[i, "tp_apres_sl"] = "n/d"
    return j, msgs

def _bloc_stats(df, titre, colonne, ordre=None):
    lignes = [f"\n### {titre}\n", "| | Trades | Gagnants | Taux | R moyen | R total |", "|---|---|---|---|---|---|"]
    groupes = df.groupby(colonne, observed=True)
    cles = ordre if ordre else sorted(groupes.groups.keys(), key=str)
    for k in cles:
        if k not in groupes.groups: continue
        g = groupes.get_group(k)
        n = len(g); w = int((g.resultat_R > 0).sum())
        lignes.append(f"| {k} | {n} | {w} | {100*w/n:.0f} % | {g.resultat_R.mean():+.2f} | {g.resultat_R.sum():+.2f} |")
    return "\n".join(lignes)

def _diagnostic(clos):
    """V5.1 : où se perd l'argent — SL trop serré, TP trop loin, ou mauvaises entrées ?"""
    d = clos[clos.ambigu.isin(["OUI", "NON"])].copy()
    out = ["\n## 🔍 Diagnostic entrée / SL / TP\n"]
    if not len(d):
        return out + ["Pas encore de trade avec MFE/MAE calculés."]
    for c in ("mfe_R", "mae_R", "resultat_R", "rr"):
        d[c] = d[c].astype(float)
    pertes, gains = d[d.statut == "SL"], d[d.resultat_R > 0]
    out.append(f"_Basé sur {len(d)} trades clôturés avec données complètes._\n")
    if len(pertes):
        out.append(f"- Pertes en bougie ambiguë (TP et SL dans la même M15, comptées SL) : "
                   f"**{(pertes.ambigu == 'OUI').sum()}/{len(pertes)}**")
        for x in (0.5, 1.0, 1.5):
            out.append(f"- Perdants passés par **+{x} R** avant le SL : {(pertes.mfe_R >= x).sum()}/{len(pertes)}")
        post = pertes[pertes.tp_apres_sl.isin(["OUI", "NON"])]
        if len(post):
            out.append(f"- Perdants dont le TP a été touché **après** le SL (≤ {JOURNAL_EXPIRE_H} h) : "
                       f"**{(post.tp_apres_sl == 'OUI').sum()}/{len(post)}** → élevé = SL trop serré")
    if len(gains):
        out.append(f"- Gagnants : recul moyen avant de gagner (MAE) **{gains.mae_R.mean():+.2f} R**, "
                   f"pire {gains.mae_R.min():+.2f} R → proche de 0 = SL resserrable")
    out.append(f"- RR visé moyen : {d.rr.mean():.2f} | MFE moyen : {d.mfe_R.mean():+.2f} R | "
               f"MFE médian : {d.mfe_R.median():+.2f} R → MFE médian très inférieur au RR = TP trop loin")
    if "px_signal" in d and d.px_signal.notna().any():
        g = d[d.px_signal.notna()]
        ecart = ((g.px_signal - g.entree).abs() / (g.entree - g.sl).abs()).mean()
        out.append(f"- Écart moyen prix réel / niveau d'entrée : **{ecart:.2f} R** (coût caché d'un ordre Market)")

    out += ["\n### Simulation : et si le TP était fixe ?\n",
            "_Approximation : un trade gagne X R si son MFE a atteint X R avant le SL ; sinon résultat inchangé._\n",
            "| TP | Gagnants | Taux | R moyen | R total |", "|---|---|---|---|---|"]
    def ligne(nom, r):
        w = int((r > 0).sum())
        return f"| {nom} | {w}/{len(r)} | {100*w/len(r):.0f} % | {r.mean():+.2f} | {r.sum():+.2f} |"
    out.append(ligne("Actuel", d.resultat_R))
    for x in (1.0, 1.5, 2.0):
        out.append(ligne(f"{x} R", pd.Series(np.where(d.mfe_R >= x, x, d.resultat_R))))
    return out

def ecrire_stats(j):
    fantomes = j[j.filtre.astype(str).isin(["", "nan"]) == False]          # V5.0
    j = j[j.filtre.astype(str).isin(["", "nan"])]                           # stats = signaux réels
    clos = j[j.statut.isin(CLOS)].copy()
    en_cours = int((j.statut == "EN_COURS").sum())
    out = ["# 📒 Journal Crypto Pépite — statistiques\n",
           f"Signaux enregistrés : **{len(j)}** — clôturés : **{len(clos)}** — en cours : **{en_cours}**\n",
           "_Hypothèses : entrée au niveau d'entrée du signal ; SL compté si TP et SL sont touchés "
           f"dans la même bougie M15 ; clôture au prix du moment après {JOURNAL_EXPIRE_H} h. "
           "Résultats en R bruts (1 R = distance entrée–SL), hors frais._\n"]
    if len(clos):
        clos["resultat_R"] = clos.resultat_R.astype(float)
        n = len(clos); w = int((clos.resultat_R > 0).sum())
        out.append("## Global\n")
        out.append(f"- Taux de réussite : **{100*w/n:.0f} %** ({w}/{n})")
        out.append(f"- Espérance : **{clos.resultat_R.mean():+.2f} R** par trade")
        out.append(f"- Total : **{clos.resultat_R.sum():+.2f} R** (≈ {clos.resultat_R.sum()*RISQUE:+.2f} USDT avec {RISQUE} USDT de risque)")
        out.append(f"- Durée moyenne : {clos.duree_h.astype(float).mean():.1f} h")
        clos["tranche_score"] = pd.cut(clos.score.astype(float), [0, 79.5, 89.5, 100], labels=["60-79", "80-89", "90-100"])
        out.append(_bloc_stats(clos, "Par tranche de score", "tranche_score", ["60-79", "80-89", "90-100"]))
        out.append(_bloc_stats(clos, "Par setup", "setup"))
        out.append(_bloc_stats(clos, "Par contexte BTC", "btc_ctx", ["sens", "neutre", "contre", "n/d"]))
        out.append(_bloc_stats(clos, "Par sens", "sens", ["LONG", "SHORT"]))
        # V5.3 : liquidité (les anciens signaux sans volume enregistré sont en « n/d »)
        tr = pd.cut(pd.to_numeric(clos.volume_24h_M, errors="coerce"), [0, PETITE_PAIRE / 1e6, 50, float("inf")],
                    labels=["🐜 < 15 M", "15-50 M", "> 50 M"])
        clos["liquidite"] = tr.astype(object).where(tr.notna(), "n/d")
        out.append(_bloc_stats(clos, "Par liquidité (volume 24h USDT)", "liquidite", ["> 50 M", "15-50 M", "🐜 < 15 M", "n/d"]))
        out += _diagnostic(clos)                                             # V5.1
        if n < 30:
            out.append(f"\n⚠️ Seulement {n} trades clôturés : trop peu pour conclure (vise au moins 30 à 50).")
    else:
        out.append("Aucun signal clôturé pour l'instant.")
    # V5.0 : signaux bloqués par le filtre « jamais contre BTC », suivis sans être tradés
    f_clos = fantomes[fantomes.statut.isin(CLOS)].copy()
    out.append(f"\n## 👻 Signaux filtrés (contre BTC, NON tradés)\n")
    out.append(f"Enregistrés : **{len(fantomes)}** — clôturés : **{len(f_clos)}** — "
               f"en cours : **{int((fantomes.statut == 'EN_COURS').sum())}**\n")
    if len(f_clos):
        f_clos["resultat_R"] = f_clos.resultat_R.astype(float)
        fn = len(f_clos); fw = int((f_clos.resultat_R > 0).sum())
        out.append(f"- Taux de réussite : **{100*fw/fn:.0f} %** ({fw}/{fn})")
        out.append(f"- R total évité : **{f_clos.resultat_R.sum():+.2f} R** "
                   "(négatif = le filtre t'a fait économiser, positif = il t'a coûté)")
    with open(STATS, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

# ---------------- MAIN ----------------
def scan():
    FANTOMES.clear()                                        # V5.0
    print(f"CRYPTO PÉPITE V5.3 — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    choisir_source_oi()
    df, info = tickers(), instruments()
    n0 = len(df)
    liq = df[(df.turnover24h >= MIN_TURNOVER) & (df.spread <= MAX_SPREAD)]
    liq = liq.sort_values("turnover24h", ascending=False).head(SHORTLIST)
    print(f"{n0} paires USDT → {len(liq)} liquides analysées en H4/H1/M15…")

    contexte_btc()

    results = []
    for i, (_, row) in enumerate(liq.iterrows(), 1):
        try:
            r = analyse(row, info.get(row.symbol, {}))
            if r: results.append(r)
        except Exception as ex:
            print(f"  {row.symbol} : erreur {ex}")
        if i % 10 == 0: print(f"  {i}/{len(liq)}…")
        time.sleep(0.15)

    src = OI_SOURCE[0] if OI_SOURCE else "aucune source"
    print(f"OI récupéré via {src} : {OI_STATS['ok']} paires OK / {OI_STATS['ko']} n/d")

    # V4.4 : règles plus strictes si BTC neutre en H4 ET H1
    btc_sans_dir = BTC_FILTRE and BTC_CTX is not None and BTC_CTX["n_neutre"] == 2
    score_min = SCORE_MIN_BTC_NEUTRE if btc_sans_dir else SCORE_MIN
    max_now   = MAX_NOW_BTC_NEUTRE if btc_sans_dir else MAX_TRADE_NOW

    ok = sorted([r for r in results if r["decision"] != "NO TRADE"], key=lambda r: -r["score"])
    top = [r for r in ok if r["score"] >= score_min][:MAX_TOP]

    n_now = 0
    for r in top:
        if r["decision"] == "TRADE NOW":
            n_now += 1
            if n_now > max_now:
                r["decision"] = "WAIT"
                r["pourquoi"] = "plafond de TRADE NOW atteint (BTC sans direction) — un seul trade à la fois"

    pd.DataFrame([{k: v for k, v in r.items() if k not in ("inf", "sup", "res", "zone")}
                  for r in results]).to_csv("scan_pepite.csv", index=False)

    alerte = alerte_btc_neutre()
    if alerte: print("\n" + alerte)
    if not top:
        print(f"\nAucun Crypto Pépite tradable actuellement (score mini {score_min}).")
    else:
        if max(r["score"] for r in top) < 70:
            print("\nℹ️ Aucun setup au-dessus de 70/100 : prudence.")
        for r in top: print(rapport(r))
    print("\n« Ne pas trader est aussi une décision de trading. »")

    # V4.5 : Telegram — uniquement les TRADE NOW pas encore envoyés
    etat, maintenant = charger_etat(), time.time()
    nouveaux = [r for r in top if r["decision"] == "TRADE NOW"
                and maintenant - etat.get(cle_signal(r), 0) > DEDUP_HEURES * 3600]
    # V4.8 : journal — suivi des signaux en cours, puis ajout des nouveaux
    journal = charger_journal()
    journal, clotures = evaluer_journal(journal)
    for m in clotures:
        print(m)
        if not m.startswith("👻"): telegram(m)               # V5.0 : pas d'alerte pour les fantômes
    journal = ajouter_au_journal(journal, nouveaux, maintenant)
    # V5.0 : TRADE NOW bloqués (contre BTC) -> journal fantôme, sans alerte
    fantomes = []
    if JOURNAL_FANTOMES:
        fantomes = [r for r in FANTOMES if r["decision_brute"] == "TRADE NOW" and r["score"] >= score_min
                    and maintenant - etat.get("FANTOME|" + cle_signal(r), 0) > DEDUP_HEURES * 3600]
        journal = ajouter_au_journal(journal, fantomes, maintenant, filtre=FILTRE_CONTRE_BTC)
        for r in fantomes: etat["FANTOME|" + cle_signal(r)] = maintenant
    journal.to_csv(JOURNAL, index=False)
    ecrire_stats(journal)
    print(f"Journal : {len(nouveaux)} ajouté(s), {len(fantomes)} fantôme(s) contre BTC, {len(clotures)} clôturé(s), "
          f"{int((journal.statut == 'EN_COURS').sum())} en cours")

    for r in nouveaux:
        entete = f"🚨 CRYPTO PÉPITE — TRADE NOW — {datetime.now(timezone.utc):%H:%M} UTC"
        if alerte_petite_paire(r): entete += f"\n🐜 PETITE PAIRE — {r['symbol']}"
        entete += "\n" + resume_btc()
        if alerte: entete += "\n" + alerte
        telegram(entete + "\n" + rapport(r) + f"\n📈 Graphique TradingView (M15) : {lien_tv(r)}")
        telegram(ligne_pepite(r))       # message séparé : appui long -> Copier
        etat[cle_signal(r)] = maintenant
    sauver_etat(etat)
    print(f"Telegram : {len(nouveaux)} nouveau(x) TRADE NOW envoyé(s)")

    # V4.9 : PREPARE à fort score (clé distincte, pour ne pas bloquer le futur TRADE NOW)
    n_prep = 0
    if PREPARE_ALERTE:
        prepares = [r for r in ok if r["decision"] == "PREPARE" and r["score"] >= PREPARE_SCORE_MIN
                    and maintenant - etat.get("PREPARE|" + cle_signal(r), 0) > DEDUP_HEURES * 3600]
        for r in prepares:
            entete = (f"🟡 CRYPTO PÉPITE — PREPARE (score {r['score']}) — {datetime.now(timezone.utc):%H:%M} UTC\n"
                      + (f"🐜 PETITE PAIRE — {r['symbol']}\n" if alerte_petite_paire(r) else "")
                      + "Pas encore déclenché : attendre la bougie de rejet M15 (alerte TRADE NOW).\n"
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
    except BaseException as ex:                             # SystemExit compris (géoblocage…)
        if isinstance(ex, KeyboardInterrupt): raise
        msg = f"⚠️ CRYPTO PÉPITE : le scan a échoué ({type(ex).__name__}) : {ex}"
        print(msg)
        telegram(msg)
        raise

if __name__ == "__main__":
    main()
