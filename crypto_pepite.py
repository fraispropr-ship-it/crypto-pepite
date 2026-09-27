# ==============================================================================
#  CRYPTO PÉPITE V4.6 — Scanner intraday Zoomex Futures (USDT perpetuals)
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
MIN_TURNOVER  = 5_000_000    # volume 24h minimum (USDT)
MAX_SPREAD    = 0.0015       # 0,15 % max
MAX_MOVE_24H  = 0.15         # anti-FOMO : > 15 % sur 24h = mouvement passé
SHORTLIST     = 60           # nb de paires analysées en détail
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

NEUTRE = "NEUTRE/RANGE"

S = requests.Session()
OI_STATS = {"ok": 0, "ko": 0}
OI_SOURCE = None             # choisie automatiquement au démarrage
BTC_CTX   = None             # contexte BTC calculé une fois par scan

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
    """Zones S/R à partir des pivots H1 regroupés (largeur mini 0,3 ATR)."""
    d = df.tail(lookback).reset_index(drop=True)
    pts = []
    for i in range(k, len(d) - k):
        if d.h.iloc[i] == d.h.iloc[i-k:i+k+1].max(): pts.append(d.h.iloc[i])
        if d.l.iloc[i] == d.l.iloc[i-k:i+k+1].min(): pts.append(d.l.iloc[i])
    pts.sort()
    clusters = []
    for p in pts:
        if clusters and p - clusters[-1][-1] <= 0.5 * a: clusters[-1].append(p)
        else: clusters.append([p])
    out = []
    for c in clusters:
        lo, hi = min(c), max(c)
        if hi - lo < 0.3 * a:
            m = (lo + hi) / 2; lo, hi = m - 0.15 * a, m + 0.15 * a
        out.append(dict(lo=lo, hi=hi, touches=len(c)))
    return out

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
    cl, lows, highs = m15.c, m15.l, m15.h
    setups = []

    if sup:   # ---- LONG ----
        z = sup[0]
        if cl.iloc[-1] > z["hi"] and (cl.iloc[-9:-1] < z["hi"]).any() and z["touches"] >= 2:
            setups.append(dict(sens="LONG", type="Cassure confirmée (clôture M15) + retest",
                               entry=z["hi"], sl=z["lo"] - 0.25 * a1, trig=z["hi"], dir="haut",
                               deja=True, zone=z))
        elif z["lo"] <= px <= z["hi"] + 0.5 * a1:
            touched = (lows.iloc[-8:] <= z["hi"]).any()
            setups.append(dict(sens="LONG", type="Rebond sur support H1",
                               entry=z["hi"], sl=z["lo"] - 0.3 * a1, trig=z["hi"], dir="haut",
                               deja=touched and cl.iloc[-1] > z["hi"], zone=z))
    if res:   # ---- SHORT ----
        z = res[0]
        if cl.iloc[-1] < z["lo"] and (cl.iloc[-9:-1] > z["lo"]).any() and z["touches"] >= 2:
            setups.append(dict(sens="SHORT", type="Cassure baissière (clôture M15) + retest",
                               entry=z["lo"], sl=z["hi"] + 0.25 * a1, trig=z["lo"], dir="bas",
                               deja=True, zone=z))
        elif z["lo"] - 0.5 * a1 <= px <= z["hi"]:
            touched = (highs.iloc[-8:] >= z["lo"]).any()
            setups.append(dict(sens="SHORT", type="Rejet de résistance H1",
                               entry=z["lo"], sl=z["hi"] + 0.3 * a1, trig=z["lo"], dir="bas",
                               deja=touched and cl.iloc[-1] < z["lo"], zone=z))

    best = None
    for s in setups:
        e, sl = s["entry"], s["sl"]; rd = abs(e - sl)
        if rd <= 0: continue
        if s["sens"] == "LONG":
            tgt = next((z["lo"] for z in res if z["lo"] > e + rd), None)
            tp = tgt if tgt else e + 2 * rd
        else:
            tgt = next((z["hi"] for z in sup if z["hi"] < e - rd), None)
            tp = tgt if tgt else e - 2 * rd
        rr = abs(tp - e) / rd
        dist = abs(px - e) / a1
        contre = (s["sens"] == "LONG" and t4 == "BAISSIÈRE") or (s["sens"] == "SHORT" and t4 == "HAUSSIÈRE")
        bf = (0, False, "sans objet (BTC lui-même)") if est_btc else filtre_btc(s["sens"], corr, s["type"])
        if rr < RR_MIN: dec, why = "NO TRADE", f"RR insuffisant ({rr:.2f})"
        elif abs(row.price24hPcnt) > MAX_MOVE_24H: dec, why = "NO TRADE", "mouvement 24h déjà fait"
        elif dist > 1.0: dec, why = "NO TRADE", "prix trop loin de l'entrée (trop tard)"
        elif contre: dec, why = "WAIT", "contre-tendance H4"
        elif bf[1]: dec, why = "WAIT", "BTC contre le trade (attendre que BTC se stabilise)"
        elif s["deja"] and dist <= 0.25: dec, why = "TRADE NOW", "déclencheur atteint, prix proche de l'entrée"
        else: dec, why = "PREPARE", "déclencheur pas encore atteint"
        sc = score(s, t4, t1, vol_ratio, oi4, ch4, rr, dist, row, r1)
        sc = int(max(0, min(100, sc + bf[0])))
        cand = dict(s, symbol=sym, px=px, tp=tp, tp_theorique=tgt is None, rr=rr, dist=dist,
                    decision=dec, pourquoi=why, score=sc, t4=t4, t1=t1, t15=t15,
                    sup=sup[:2], res=res[:2], vol_ratio=vol_ratio, oi4=oi4, oi24=oi24,
                    ch4=ch4, funding=row.fundingRate, rsi_h1=r1, vwap=vwap_jour(m15),
                    atr_h1=a1, turnover=row.turnover24h, spread=row.spread,
                    ch24=row.price24hPcnt, inf=inf,
                    corr_btc=corr, btc_pts=bf[0], btc_txt=bf[2])
        if best is None or cand["score"] > best["score"]: best = cand
    return best

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
RR : {c['rr']:.2f}
Capital : {CAPITAL:.0f} USDT | Risque visé : {RISQUE} USDT (frais inclus)
Quantité : {sz['q']:.6g} tokens | Notionnel : {sz['notional']:.2f} USDT
Levier : x{sz['lev']} | Marge ≈ {sz['marge']:.2f} USDT | Risque réel au SL ≈ {sz['risque']:.2f} USDT{'  ⚠️ quantité < minimum Zoomex' if sz['trop_petit'] else ''}
Alerte TradingView : M15 — croisement vers le {c['dir']} de {arrondi(c['trig'], t)} — « Une fois par clôture de barre »
Invalidation : clôture H1 {'sous' if c['sens']=='LONG' else 'au-dessus de'} {sl}
Pourquoi maintenant : {c['pourquoi']} ; distance à l'entrée = {c['dist']:.2f} ATR H1
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

def cle_signal(r):
    """Même paire + même sens + même setup + même niveau d'entrée = même signal."""
    t = r["inf"].get("tick")
    return f"{r['symbol']}|{r['sens']}|{r['type']}|{arrondi(r['entry'], t)}"

# ---------------- MAIN ----------------
def scan():
    print(f"CRYPTO PÉPITE V4.6 — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
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
    for r in nouveaux:
        entete = f"🚨 CRYPTO PÉPITE — TRADE NOW — {datetime.now(timezone.utc):%H:%M} UTC"
        entete += "\n" + resume_btc()
        if alerte: entete += "\n" + alerte
        telegram(entete + "\n" + rapport(r))
        etat[cle_signal(r)] = maintenant
    sauver_etat(etat)
    print(f"Telegram : {len(nouveaux)} nouveau(x) TRADE NOW envoyé(s)")

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
