# ==============================================================================
#  RADAR ALT V2.3 — repère les altcoins qui ont un avantage MESURÉ (Zoomex, USDT perp)
#
#  Philosophie : la machine REPÈRE et PRÉVIENT, c'est TOI qui décides.
#  Aucune promesse de gain : voir « Ce que dit le backtest » ci-dessous.
#
#  Pourquoi la V2 : les deux figures de la V1 (continuation et retournement « W ») ont été
#  rejouées sur 13 mois (backtest_radar.py, 3 000 déclenchements). Le retournement perdait
#  −0,17 R par alerte de façon constante, la continuation était nulle, et aucun filtre
#  (feu BTC, volume, extension, taille du stop) ni aucune sortie ne les rendait rentables.
#  Elles sont remplacées par les deux seules familles restées positives sur les deux moitiés
#  de l'historique :
#
#   🏆 LEADER (LONG) : l'alt entre dans le top 20 % des paires liquides à la fois sur 7 jours
#      et sur 30 jours, avec une tendance haussière en H4 (moyenne 20 > moyenne 50) et en
#      journalier (clôture > moyenne 50 j). On achète la force, pas le creux.
#   📉 CASSURE (SHORT) : clôture H4 sous le plus bas des 60 derniers jours.
#      On vend la faiblesse confirmée, pas le sommet.
#
#  Un signal = un état NOUVEAU : la condition est vraie à la clôture H4 alors qu'elle ne
#  l'était sur aucune des 18 bougies H4 précédentes (3 jours). Au plus MAX_PAR_PASSAGE
#  signaux par sens et par clôture H4 (les paires les plus liquides d'abord).
#
#  Ticket : entrée au prix du signal, SL à 2 ATR H4, objectif 3 R, 7 jours maximum.
#
#  Ce que dit le backtest (déc. 2025 – nov. 2026, frais et glissement inclus, backtest_radar.py) :
#   - Leader  : 473 signaux, 33 % de gagnants, +0,16 R en moyenne, identique sur les deux moitiés ;
#   - Cassure : 212 signaux, 53 % de gagnants, +0,40 R en moyenne, MAIS +0,63 R sur la première
#     moitié et −0,15 R sur la seconde : le short ne gagne que pendant les vraies baisses ;
#   - ensemble : environ 14 signaux par semaine, 29 semaines positives sur 49, pire série −35 R.
#  Deux tiers des leaders touchent leur SL : le gain vient d'une minorité de gros gagnants.
#  C'est une base plus saine que la V1 (−0,4 R par alerte en réel), pas une machine à gagner.
#
#  Messages Telegram :
#   - une ALERTE immédiate à chaque signal, avec le ticket copiable ;
#   - un RÉSUMÉ toutes les 4 h, juste après la clôture H4, jour et nuit (voir SILENCE_NUIT) :
#     un bloc par paire, LONG ou SHORT, avec la consigne (y aller / attendre / ne pas
#     entrer), le déclenchement et les niveaux (entrée, SL, TP).
#
#  Suivi automatique : chaque signal est suivi (objectif, SL, durée max) et enregistré dans
#  radar_journal.csv (types « leader » et « cassure_bas »), pour comparer réel et backtest.
#
#  Fichiers : radar_etat.json (mémoire du radar), radar_journal.csv (signaux clôturés).
#  Lancement : .github/workflows/radar.yaml, toutes les heures (cron-job.org, minute 2).
#  Secrets : TELEGRAM_TOKEN et TELEGRAM_CHAT_ID (les mêmes que Crypto Pépite).
#  Cryptos uniquement : actions, ETF, or, pétrole, indices… sont écartés (liste HORS_CRYPTO).
#  NE couvre PAS : news / macro -> à vérifier toi-même avant d'entrer.
# ==============================================================================
import json, math, os, re, sys, time
from datetime import datetime, timezone
from decimal import Decimal
from html import escape, unescape
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

VERSION = "2.3"

# ---------------- RÉGLAGES ----------------
LIQ_MIN        = 10_000_000   # volume 24 h minimum (USDT)
PAIRES_MAX     = 100          # paires examinées (les plus liquides)
UNIVERS_MIN    = 20           # en dessous de 20 paires classables, pas de classement de force
FORCE_MIN      = 0.80         # leader : dans le top 20 % sur 7 j ET sur 30 j
FORCE_PROCHE   = 0.70         # « à surveiller » : dans le top 30 %
BARRES_7J      = 42           # 7 jours en bougies H4
BARRES_30J     = 180          # 30 jours en bougies H4
BARRES_BAS     = 360          # plus bas de référence : 60 jours en bougies H4
REPOS_H4       = 18           # signal = état nouveau : pas vrai sur les 18 H4 précédentes (3 j)
MAX_PAR_PASSAGE = 2           # signaux maximum par sens à chaque clôture H4
RETARD_MAX_H   = 2            # passage trop en retard après la clôture H4 : pas d'alerte
STOP_ATR       = 2.0          # SL à 2 ATR H4 de l'entrée
OBJECTIF_R     = 3.0          # objectif indicatif
SUIVI_MAX_H    = 168          # suivi d'un signal : 7 jours maximum
SILENCE_NUIT   = None         # résumé jour et nuit ; mettre (23, 7) pour le couper de 23 h à 7 h (heure de Paris)
RISQUE         = 1.0          # USDT risqués par trade (pour le ticket)
MARGE_CIBLE    = 20.0         # marge max souhaitée par trade (USDT)
FRAIS_TAKER    = 0.0006
MAX_LISTE      = 5
ENTREE_OK      = (-0.5, 0.3)  # résumé : signal encore prenable si son résultat en cours est entre −0,5 R et +0,3 R

# Tout ce qui n'est pas une crypto (comparé au nom sans « USDT » ni préfixe « 1000 »).
# Si une action ou une matière première passe encore, ajoute-la ici.
HORS_CRYPTO = {
    # métaux, énergie, matières premières
    "XAU", "XAUT", "PAXG", "XAG", "XPT", "XPD", "GOLD", "SILVER", "COPPER", "HG",
    "CL", "BZ", "WTI", "BRENT", "OIL", "USOIL", "UKOIL", "NG", "NATGAS", "GAS",
    # indices et ETF
    "SPX", "SPX500", "NDX", "NAS100", "US30", "US500", "DJI", "DAX", "SPY", "QQQ", "IWM",
    "SOXL", "SOXS", "TQQQ", "SQQQ", "GLD", "SLV", "EWY", "EWJ",
    # devises
    "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "CNH",
    # actions
    "TSLA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "NFLX", "AMD", "INTC",
    "MSTR", "COIN", "HOOD", "PLTR", "JPM", "GS", "BAC", "MRVL", "AVGO", "TSM", "ASML",
    "ORCL", "CRM", "ADBE", "UBER", "BABA", "PDD", "SNDK", "MU", "SKHY", "SKHYNIX",
    "SAMSUNG", "ARM", "SMCI", "CRCL", "GME", "AMC", "DIS", "NKE", "KO", "PEP", "WMT",
    "COST", "PYPL", "SHOP", "RIVN", "LCID", "NIO", "BA", "LMT", "RTX", "XOM", "CVX",
    "VRTX", "LLY", "NVO", "PFE", "MRNA", "UNH", "JNJ", "IBM", "CSCO", "QCOM", "TXN",
    "SPCX", "SPACEX", "OPENAI", "ANTHROPIC", "CRWV", "RDDT", "APP", "SNOW", "NET",
    "MARA", "RIOT", "CLSK", "IREN", "BMNR", "SBET", "GLXY", "CIRCLE", "FIG", "BLSH",
}
MOTS_HORS_CRYPTO = ("STOCK", "XSTOCK")
TYPES_HORS_CRYPTO = ("stock", "xstock", "equity", "commodity", "metal", "forex", "index", "etf", "tradfi")

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ETAT    = "radar_etat.json"
JOURNAL = "radar_journal.csv"
PARIS   = ZoneInfo("Europe/Paris")
H1, H4, JOUR = 3_600_000, 14_400_000, 86_400_000

BASE = "https://openapi.zoomex.com/cloud/trade/v3/market/"
SESS = requests.Session()


# ---------------- DONNÉES ----------------
def api(path, **params):
    for essai in range(3):
        try:
            r = SESS.get(BASE + path, params=params, timeout=20)
            if r.status_code in (403, 451):
                return None
            j = r.json()
            if j.get("retCode") == 0:
                return j["result"]
        except Exception:
            pass
        time.sleep(1 + essai)
    return None


def bougies(sym, iv, limit, maintenant):
    """Bougies CLÔTURÉES uniquement, triées par date."""
    res = api("kline", category="linear", symbol=sym, interval=iv, limit=limit)
    if not isinstance(res, dict) or not res.get("list"):
        return None
    df = pd.DataFrame(res["list"]).iloc[:, :6]
    df.columns = ["t", "o", "h", "l", "c", "v"]
    df = df.astype(float).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    duree = {"15": 900_000, "60": H1, "240": H4, "D": JOUR}[iv]
    return df[df.t + duree <= maintenant].reset_index(drop=True)


def univers():
    res = api("tickers", category="linear")
    if not res:
        return [], {}, {}
    df = pd.DataFrame(res["list"])
    for c in ["turnover24h", "lastPrice"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df.symbol.str.endswith("USDT") & (df.turnover24h >= LIQ_MIN)]
    df = df.sort_values("turnover24h", ascending=False).head(PAIRES_MAX)
    return list(df.symbol), dict(zip(df.symbol, df.lastPrice)), dict(zip(df.symbol, df.turnover24h))


def instruments():
    res = api("instruments-info", category="linear", limit=1000)
    info = {}
    for it in (res or {}).get("list", []):
        try:
            # type d'instrument, si Zoomex le précise (ex. « xstocks », « commodity »)
            genre = " ".join(str(it.get(k, "")) for k in ("symbolType", "contractType", "category", "tag")).lower()
            info[it["symbol"]] = dict(tick=float(it["priceFilter"]["tickSize"]),
                                      step=float(it["lotSizeFilter"]["qtyStep"]),
                                      minq=float(it["lotSizeFilter"]["minOrderQty"]),
                                      hors_crypto=any(m in genre for m in TYPES_HORS_CRYPTO))
        except Exception:
            pass
    return info


def base_de(sym):
    b = sym[:-4] if sym.endswith("USDT") else sym
    for pre in ("1000000", "10000", "1000", "100"):
        if b.startswith(pre) and len(b) > len(pre):
            return b[len(pre):]
    return b


def est_crypto(sym, info):
    """Faux pour les actions, ETF, matières premières, indices et devises."""
    b = base_de(sym)
    if b in HORS_CRYPTO or any(m in sym for m in MOTS_HORS_CRYPTO):
        return False
    return not info.get(sym, {}).get("hors_crypto", False)


# ---------------- INDICATEURS ----------------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df.c.shift()
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ---------------- DÉTECTION (H4) ----------------
SENS = {"leader": 1, "cassure_bas": -1}


def mesures(h4, d):
    """Mesures d'une paire sur sa dernière bougie H4 clôturée (None si historique trop court)."""
    if h4 is None or len(h4) < BARRES_30J + 1:
        return None
    c = h4.c
    px, a = float(c.iloc[-1]), float(atr(h4).iloc[-1])
    if not (a > 0 and px > 0):
        return None
    m = dict(prix=px, atr=a, t=float(h4.t.iloc[-1]) + H4,
             r7=px / float(c.iloc[-1 - BARRES_7J]) - 1,
             r30=px / float(c.iloc[-1 - BARRES_30J]) - 1,
             h4_haussier=bool(ema(c, 20).iloc[-1] > ema(c, 50).iloc[-1]),
             jour_haussier=bool(d is not None and len(d) >= 60 and d.c.iloc[-1] > ema(d.c, 50).iloc[-1]),
             bas60=None)
    if len(h4) >= BARRES_BAS + 1:
        m["bas60"] = float(h4.l.iloc[-1 - BARRES_BAS:-1].min())      # sans la bougie en cours
    return m


def detecter(M):
    """M = {paire: mesures}. Ajoute force7 / force30 (rang 0-1 dans l'univers) à chaque paire
    et retourne {(paire, type): mesures} pour les paires qui remplissent une condition."""
    out = {}
    if len(M) >= UNIVERS_MIN:
        f7 = pd.Series({s: m["r7"] for s, m in M.items()}).rank(pct=True)
        f30 = pd.Series({s: m["r30"] for s, m in M.items()}).rank(pct=True)
        for s, m in M.items():
            m["force7"], m["force30"] = float(f7[s]), float(f30[s])
            if min(m["force7"], m["force30"]) > FORCE_MIN and m["h4_haussier"] and m["jour_haussier"]:
                out[(s, "leader")] = m
    for s, m in M.items():
        if m["bas60"] is not None and m["prix"] < m["bas60"]:
            out[(s, "cassure_bas")] = m
    return out


def nouveaux_signaux(candidats, vus, bloc):
    """Garde les états NOUVEAUX (pas vus depuis plus de REPOS_H4 bougies) et met `vus` à jour.
    `bloc` = heure de clôture (ms) de la bougie H4 analysée."""
    neufs = []
    for (sym, typ) in candidats:
        cle = f"{sym}|{typ}"
        dernier = vus.get(cle)
        if dernier is None or bloc - dernier > REPOS_H4 * H4:
            neufs.append((sym, typ))
        vus[cle] = bloc
    for cle in [k for k, t in vus.items() if bloc - t > 10 * REPOS_H4 * H4]:
        del vus[cle]                                       # ménage des très vieilles entrées
    return neufs


def retenir(neufs, volume):
    """Au plus MAX_PAR_PASSAGE signaux par sens, les paires les plus liquides d'abord."""
    gardes = []
    for typ in SENS:
        du_type = sorted([x for x in neufs if x[1] == typ], key=lambda x: -volume.get(x[0], 0))
        gardes += du_type[:MAX_PAR_PASSAGE]
    return gardes


def ticket(prix, a, typ, tick=None):
    """Entrée, SL (2 ATR H4) et objectif (3 R) pour un signal."""
    sens = SENS[typ]
    e = arrondi(prix, tick)
    sl = arrondi(e - sens * STOP_ATR * a, tick)
    return e, sl, arrondi(e + sens * OBJECTIF_R * abs(e - sl), tick)


# ---------------- OUTILS ----------------
def arrondi(x, tick):
    return round(round(x / tick) * tick, 10) if tick else x


def fmt(x, pas=None):
    if pas:
        dec = max(0, -Decimal(str(pas)).normalize().as_tuple().exponent)
        return f"{x:.{dec}f}"
    return f"{x:.8f}".rstrip("0").rstrip(".")


def sizing(e, sl, inf):
    dist = abs(e - sl)
    q = RISQUE / (dist + 2 * FRAIS_TAKER * e)
    step = inf.get("step")
    if step:
        q = math.floor(q / step) * step
    notional = q * e
    lev = max(1, math.ceil(notional / MARGE_CIBLE))
    return dict(q=q, notional=notional, lev=lev, marge=notional / lev,
                trop_petit=bool(inf.get("minq") and q < inf["minq"]))


def lien_tv(sym):
    return f"https://www.tradingview.com/chart/?symbol=ZOOMEX:{sym}.P&interval=240"


def telegram(texte):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("(Telegram non configuré : message non envoyé)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for m in decouper(texte):
        data = dict(chat_id=TELEGRAM_CHAT_ID, text=m, parse_mode="HTML", disable_web_page_preview=True)
        try:
            r = requests.post(url, data=data, timeout=15)
            if r.status_code == 400:                    # mise en forme refusée -> texte simple
                data.pop("parse_mode")
                data["text"] = unescape(re.sub(r"<[^>]+>", "", m))
                r = requests.post(url, data=data, timeout=15)
            print("Telegram :", "envoyé" if r.ok else f"échec ({r.status_code} {r.text[:120]})")
        except Exception as e:
            print(f"Telegram : échec ({e})")
        time.sleep(0.4)


def decouper(texte, n=3800):
    morceaux, bloc = [], ""
    for ligne in texte.split("\n"):
        if len(bloc) + len(ligne) + 1 > n:
            morceaux.append(bloc)
            bloc = ""
        bloc += ligne + "\n"
    return morceaux + ([bloc] if bloc.strip() else [])


# ---------------- CONTEXTE BTC ----------------
def contexte(maintenant, quotidiens):
    d = bougies("BTCUSDT", "D", 260, maintenant)
    h4 = bougies("BTCUSDT", "240", 120, maintenant)
    if d is None or h4 is None or len(d) < 200:
        return dict(feu="⚪", texte="₿ BTC : indisponible")
    m200 = float(d.c.rolling(200).mean().iloc[-1])
    fond = float(d.c.iloc[-1]) > m200
    largeur = np.mean([float(x.c.iloc[-1]) > float(ema(x.c, 50).iloc[-1])
                       for x in quotidiens if x is not None and len(x) >= 60]) * 100 if quotidiens else 50
    e20, e50 = ema(h4.c, 20).iloc[-1], ema(h4.c, 50).iloc[-1]
    t4 = "haussier ↗️" if h4.c.iloc[-1] > e50 and e20 > e50 else "baissier ↘️" if h4.c.iloc[-1] < e50 and e20 < e50 else "en range ➡️"
    feu = "🟢" if fond and largeur >= 50 else "🟠" if fond or largeur >= 50 else "🔴"
    txt = (f"{feu} ₿ BTC {float(h4.c.iloc[-1]):,.0f} · {'au-dessus' if fond else 'en dessous'} de sa moyenne "
           f"200 j · H4 {t4} · {largeur:.0f} % des alts au-dessus de leur moyenne 50 j").replace(",", " ")
    return dict(feu=feu, texte=txt)


# ---------------- ÉTAT ET JOURNAL ----------------
def charger_etat():
    try:
        with open(ETAT, encoding="utf-8") as f:
            etat = json.load(f)
    except Exception:
        etat = {}
    if etat.get("version") != 2:
        # Passage V1 -> V2 : on garde les déclenchements V1 en cours pour finir de les suivre
        # (72 h, objectif d'origine), on oublie les pré-setups V1. `vus` absent = amorçage.
        suivis = {}
        for sid, s in etat.get("setups", {}).items():
            if s.get("etape") in ("declenche", "trop_tard") and s.get("t_decl"):
                suivis[sid] = dict(id=sid, sym=s["sym"], type=s["type"], sens=1, t_decl=s["t_decl"],
                                   entree=s["entree"], sl=s["sl"], objectif=s["objectif"], objectif_r=2.0,
                                   max_h=72, feu=s.get("feu", ""), date_decl=s.get("date_decl", ""),
                                   info=s.get("info", {}))
        etat = dict(version=2, suivis=suivis, dernier_resume=etat.get("dernier_resume", 0), dernier_h4=0)
    etat.setdefault("suivis", {})
    return etat


def sauver_etat(etat):
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=1)


COLS = ["id", "symbole", "type", "date_declenchement", "entree", "sl", "objectif", "statut",
        "resultat_R", "mfe_R", "duree_h", "feu", "info"]


def journaliser(s, statut, r, mfe, duree):
    ligne = dict(id=s["id"], symbole=s["sym"], type=s["type"], date_declenchement=s["date_decl"],
                 entree=s["entree"], sl=s["sl"], objectif=s["objectif"], statut=statut,
                 resultat_R=round(r, 2), mfe_R=round(mfe, 2), duree_h=round(duree, 1),
                 feu=s.get("feu", ""), info=json.dumps(s.get("info", {}), ensure_ascii=False))
    existe = os.path.exists(JOURNAL)
    pd.DataFrame([ligne], columns=COLS).to_csv(JOURNAL, mode="a", header=not existe, index=False)


def suivre(s, h1):
    """Suit un signal sur les bougies H1 : SL (prioritaire), objectif, ou durée maximale.
    Retourne (statut, résultat en R, meilleur gain latent en R, durée en h, résultat latent en R)."""
    b = h1[h1.t >= s["t_decl"]]
    sens, e, sl, tp = s.get("sens", 1), s["entree"], s["sl"], s["objectif"]
    risque = abs(e - sl)
    max_h = s.get("max_h", SUIVI_MAX_H)
    mfe = 0.0
    for _, x in b.iterrows():
        pire, mieux = (x.l, x.h) if sens == 1 else (x.h, x.l)
        duree = (x.t + H1 - s["t_decl"]) / H1
        if sens * (pire - sl) <= 0:
            return "SL", -1.0, mfe, duree, -1.0
        mfe = max(mfe, sens * (mieux - e) / risque)
        if sens * (mieux - tp) >= 0:
            return "OBJECTIF", s.get("objectif_r", OBJECTIF_R), mfe, duree, None
    latent = sens * (float(b.c.iloc[-1]) - e) / risque if len(b) else 0.0
    if len(b) and (b.t.iloc[-1] + H1 - s["t_decl"]) / H1 >= max_h:
        return "EXPIRE", latent, mfe, max_h, latent
    return None, None, mfe, None, latent


# ---------------- MESSAGES ----------------
NOMS = {"leader": "🏆 Leader · LONG", "cassure_bas": "📉 Cassure · SHORT",
        "continuation": "📈 Continuation (V1)", "retournement": "🔄 Retournement (V1)"}


def lien(sym, texte="Graphique TradingView H4"):
    return f'<a href="{escape(lien_tv(sym), quote=True)}">{texte}</a>'


def pourquoi(typ, m, tick=None):
    if typ == "leader":
        return (f"Top {max(1, round(100 * (1 - m['force7'])))} % sur 7 j ({100 * m['r7']:+.0f} %) et top "
                f"{max(1, round(100 * (1 - m['force30'])))} % sur 30 j ({100 * m['r30']:+.0f} %) · tendance haussière H4 et journalière")
    return (f"Clôture H4 sous le plus bas des 60 derniers jours ({fmt(arrondi(m['bas60'], tick), tick)}) · "
            f"{100 * m['r30']:+.0f} % sur 30 j")


def alerte(s, m, ctx, inf):
    t, step = inf.get("tick"), inf.get("step")
    e, sl, tp = s["entree"], s["sl"], s["objectif"]
    sz = sizing(e, sl, inf)
    frais = 2 * FRAIS_TAKER * e / abs(e - sl)
    base = escape(s["sym"][:-4])
    sl_pct = 100 * abs(1 - sl / e)
    lignes = [
        f"{'🟢' if s['sens'] == 1 else '🔴'} <b>{'LONG' if s['sens'] == 1 else 'SHORT'} — {base}</b> · RADAR ALT",
        "✅ <b>Déclenché : OK pour y aller maintenant</b>",
        NOMS[s["type"]],
        f"<i>{escape(pourquoi(s['type'], m, t))}</i>",
        "",
        f"Paire : <code>{base}</code>",
        f"Sens : <code>{'LONG (achat)' if s['sens'] == 1 else 'SHORT (vente)'}</code>",
        f"Quantité : <code>{fmt(sz['q'], step)}</code> {base}",
        f"Entrée : <code>{fmt(e, t)}</code>",
        f"SL ({STOP_ATR:g} ATR H4) : <code>{fmt(sl, t)}</code>",
        f"TP ({OBJECTIF_R:g} R, indicatif) : <code>{fmt(tp, t)}</code>",
        f"Valeur : <code>{sz['notional']:.2f}</code> USDT · levier x{sz['lev']} · marge ≈ {sz['marge']:.2f} USDT",
        f"Frais ≈ {frais:.2f} R · SL à {sl_pct:.1f} % (bruit journalier {s['bruit']:.0f} %) · durée max {SUIVI_MAX_H // 24} j",
        "",
        escape(ctx["texte"]),
        "⚠️ News / macro non vérifiées · ce n'est pas un ordre : c'est toi qui décides",
        "📊 " + lien(s["sym"]),
    ]
    if sz["trop_petit"]:
        lignes.insert(4, "⚠️ Quantité sous le minimum Zoomex")
    return "\n".join(lignes)


def titre(sym, sens):
    return f"{'🟢' if sens == 1 else '🔴'} <b>{'LONG' if sens == 1 else 'SHORT'} — {escape(sym[:-4])}</b>"


def resume(etat, M, candidats, ctx, latents, maintenant_ms, info, prix):
    """Résumé en blocs : ce qu'on peut prendre maintenant, ce qu'il faut attendre, le reste."""
    maintenant = datetime.now(PARIS)
    tick = lambda s: info.get(s, {}).get("tick")
    p = lambda x, s: f"<code>{fmt(arrondi(x, tick(s)), tick(s))}</code>"
    suivis = sorted(etat["suivis"].values(), key=lambda s: -s["t_decl"])
    en_cours = {(s["sym"], s["type"]) for s in suivis}

    # 1) Signaux V2 en cours : encore prenables ou non, selon l'écart du prix avec l'entrée
    prendre, passes = [], []
    for s in suivis:
        r, px = latents.get(s["id"]), prix.get(s["sym"])
        age = (maintenant_ms - s["t_decl"]) / H1
        if s["type"] in SENS and r is not None and px and ENTREE_OK[0] <= r <= ENTREE_OK[1]:
            prendre.append("\n".join([
                titre(s["sym"], s["sens"]),
                "✅ <b>OK pour y aller maintenant</b> (prix encore proche de l'entrée du signal)",
                f"Entrée : {p(px, s['sym'])} (prix actuel)",
                f"SL : {p(s['sl'], s['sym'])}",
                f"TP : {p(s['objectif'], s['sym'])}",
                f"Signal donné il y a {age:.0f} h à {p(s['entree'], s['sym'])} · {lien(s['sym'], 'graphique')}"]))
        else:
            if s["type"] not in SENS:
                raison = "⛔ Ne pas entrer : ancien radar V1, simple suivi"
            elif r is None:
                raison = "⛔ Ne pas entrer : prix indisponible"
            elif r > ENTREE_OK[1]:
                raison = "⛔ Trop tard pour entrer : le prix est déjà parti"
            else:
                raison = "⛔ Ne pas entrer : le prix est revenu près du SL"
            passes.append("\n".join([
                titre(s["sym"], s.get("sens", 1)),
                raison,
                f"Résultat en cours : {r:+.1f} R · depuis {age:.0f} h" if r is not None else f"Depuis {age:.0f} h",
                f"Entrée {p(s['entree'], s['sym'])} · SL {p(s['sl'], s['sym'])} · TP {p(s['objectif'], s['sym'])}"]))

    # 2) SHORT en attente : prix à moins de 1 ATR au-dessus du plus bas 60 j
    attente_s = []
    for dist, s, m in sorted([((m["prix"] - m["bas60"]) / m["atr"], s, m) for s, m in M.items()
                              if m["bas60"] is not None and 0 <= (m["prix"] - m["bas60"]) / m["atr"] <= 1.0
                              and (s, "cassure_bas") not in en_cours], key=lambda x: x[0])[:MAX_LISTE]:
        px = prix.get(s, m["prix"])
        e, sl, tp = ticket(m["bas60"], m["atr"], "cassure_bas", tick(s))
        attente_s.append("\n".join([
            titre(s, -1),
            f"⏳ <b>Attendre.</b> Y aller seulement si une bougie H4 clôture sous {p(m['bas60'], s)}",
            f"Prix actuel : {p(px, s)} (déclenchement à {100 * (m['bas60'] / px - 1):+.1f} %)",
            f"Si déclenché : entrée ≈ {p(e, s)} · SL {p(sl, s)} · TP {p(tp, s)}",
            lien(s, "graphique")]))

    # 3) LONG en attente : alts fortes en tendance, pas encore dans le top du classement
    attente_l = []
    for f, s, m in sorted([(min(m["force7"], m["force30"]), s, m) for s, m in M.items()
                           if "force7" in m and min(m["force7"], m["force30"]) > FORCE_PROCHE
                           and m["h4_haussier"] and m["jour_haussier"] and (s, "leader") not in candidats],
                          key=lambda x: -x[0])[:MAX_LISTE]:
        attente_l.append("\n".join([
            titre(s, 1),
            "⏳ <b>Attendre l'alerte.</b> Pas de prix à surveiller : le signal part à une clôture H4 "
            f"si l'alt entre dans le top {100 * (1 - FORCE_MIN):.0f} % sur 7 j et sur 30 j",
            f"Aujourd'hui : top {max(1, round(100 * (1 - m['force7'])))} % sur 7 j ({100 * m['r7']:+.0f} %) · "
            f"top {max(1, round(100 * (1 - m['force30'])))} % sur 30 j ({100 * m['r30']:+.0f} %)",
            lien(s, "graphique")]))

    def section(nom, blocs):
        return ["━━━━━━━━━━━━", f"<b>{nom} : {len(blocs)}</b>", "", "\n\n".join(blocs) if blocs else "aucun", ""]

    out = [f"📡 <b>RADAR ALT — {maintenant:%d/%m %H:%M}</b>", "", escape(ctx["texte"]), ""]
    out += section("✅ À PRENDRE MAINTENANT", prendre)
    out += section("⏳ À ATTENDRE — SHORT proche du déclenchement", attente_s)
    out += section("⏳ À ATTENDRE — LONG proche du signal", attente_l)
    out += section("⛔ SIGNAUX EN COURS À NE PAS PRENDRE", passes[:2 * MAX_LISTE])
    out += ["━━━━━━━━━━━━",
            f"<i>Une alerte avec le ticket complet part à chaque déclenchement (au plus {MAX_PAR_PASSAGE} par sens "
            f"et par clôture H4, les paires les plus liquides d'abord). SL à {STOP_ATR:g} ATR H4, TP à {OBJECTIF_R:g} R. "
            f"News / macro non vérifiées. V{VERSION}</i>"]
    return "\n".join(out)


# ---------------- PROGRAMME ----------------
def main():
    print(f"RADAR ALT V{VERSION} — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    maintenant = int(time.time() * 1000)
    bloc = maintenant // H4 * H4                           # clôture de la dernière bougie H4
    syms, prix_tk, volume = univers()
    if not syms:
        print("⛔ Données Zoomex inaccessibles.")
        sys.exit(1)
    info = instruments()
    etat = charger_etat()
    suivis = etat["suivis"]

    # Cryptos uniquement (BTC est gardé pour le contexte)
    exclus = [s for s in syms if s != "BTCUSDT" and not est_crypto(s, info)]
    syms = [s for s in syms if s not in exclus]
    print(f"Écartés (hors crypto) : {', '.join(base_de(s) for s in exclus) or 'aucun'}")

    # 1) Lecture des paires
    M, h1s, bruits, quotidiens = {}, {}, {}, []
    for sym in syms:
        d = bougies(sym, "D", 120, maintenant)
        quotidiens.append(d)
        if sym == "BTCUSDT":
            continue
        h4 = bougies(sym, "240", BARRES_BAS + 40, maintenant)
        h1 = bougies(sym, "60", 200, maintenant)
        if h4 is None or h1 is None or len(h1) < 10:
            continue
        h1s[sym] = h1
        bruits[sym] = float(100 * atr(d, 20).iloc[-1] / d.c.iloc[-1]) if d is not None and len(d) > 25 else float("nan")
        m = mesures(h4, d)
        if m and m["t"] == bloc:                           # données à jour uniquement
            M[sym] = m
        time.sleep(0.05)
    for sym in sorted({s["sym"] for s in suivis.values()} - set(h1s)):
        h1 = bougies(sym, "60", 200, maintenant)           # paire sortie de la liste mais encore suivie
        if h1 is not None and len(h1) >= 10:
            h1s[sym] = h1
        time.sleep(0.05)
    ctx = contexte(maintenant, quotidiens)
    print(ctx["texte"])

    # 2) Nouveaux signaux : une seule fois par bougie H4
    candidats = detecter(M)
    signaux = []
    if etat.get("dernier_h4") != bloc and M:
        amorcage = "vus" not in etat
        vus = etat.setdefault("vus", {})
        neufs = nouveaux_signaux(candidats, vus, bloc)
        retard = (maintenant - bloc) / H1
        if amorcage:
            print(f"Amorçage V2 : {len(candidats)} état(s) déjà en place mémorisé(s), pas d'alerte.")
        elif retard > RETARD_MAX_H:
            print(f"Passage en retard de {retard:.1f} h sur la clôture H4 : {len(neufs)} signal(aux) non envoyé(s).")
        else:
            gardes = retenir(neufs, volume)
            if len(neufs) > len(gardes):
                print("Non retenus (limite par passage) : " + ", ".join(f"{s} {t}" for s, t in neufs if (s, t) not in gardes))
            for sym, typ in gardes:
                m, inf = M[sym], info.get(sym, {})
                prix = float(h1s[sym].c.iloc[-1])
                e, sl, tp = ticket(prix, m["atr"], typ, inf.get("tick"))
                if not abs(e - sl) > 0:
                    continue
                t_decl = float(h1s[sym].t.iloc[-1]) + H1
                sid = f"{sym}|{typ}|{int(bloc)}"
                s = dict(id=sid, sym=sym, type=typ, sens=SENS[typ], t_decl=t_decl, entree=e, sl=sl, objectif=tp,
                         objectif_r=OBJECTIF_R, max_h=SUIVI_MAX_H, feu=ctx["feu"], bruit=bruits.get(sym, float("nan")),
                         date_decl=datetime.fromtimestamp(t_decl / 1000, PARIS).strftime("%Y-%m-%d %H:%M"),
                         info=dict(sens="long" if SENS[typ] == 1 else "short", atr=m["atr"],
                                   r7=round(m["r7"], 4), r30=round(m["r30"], 4),
                                   force7=round(m.get("force7", float("nan")), 3),
                                   force30=round(m.get("force30", float("nan")), 3),
                                   bas60=m["bas60"], volume24h=round(volume.get(sym, 0))))
                suivis[sid] = s
                signaux.append((s, m))
        etat["dernier_h4"] = bloc

    # 3) Suivi des signaux en cours
    latents = {}
    for sid, s in list(suivis.items()):
        h1 = h1s.get(s["sym"])
        if h1 is None:
            if maintenant - s["t_decl"] > (s.get("max_h", SUIVI_MAX_H) + 6) * H1:
                journaliser(s, "EXPIRE_SANS_DONNEES", 0.0, 0.0, s.get("max_h", SUIVI_MAX_H))
                del suivis[sid]                            # clôture forcée, résultat inconnu
            continue
        statut, r, mfe, duree, latent = suivre(s, h1)
        if statut:
            journaliser(s, statut, r, mfe, duree)
            del suivis[sid]
        else:
            latents[sid] = latent

    # 4) Messages
    for s, m in signaux:
        print(f"Signal : {s['sym']} {s['type']}")
        telegram(alerte(s, m, ctx, info.get(s["sym"], {})))
    heure_paris = datetime.now(PARIS).hour
    nuit = bool(SILENCE_NUIT) and (SILENCE_NUIT[0] <= heure_paris or heure_paris < SILENCE_NUIT[1])
    bloc_h4 = maintenant // H4
    forcer = "--resume" in sys.argv
    if forcer or (etat.get("dernier_resume", 0) < bloc_h4 and not nuit):
        prix = {x: float(h.c.iloc[-1]) for x, h in h1s.items()}
        telegram(resume(etat, M, candidats, ctx, latents, maintenant, info, prix))
        etat["dernier_resume"] = bloc_h4
    n = {t: sum(1 for k in candidats if k[1] == t) for t in SENS}
    print(f"Paires classées : {len(M)} · leaders : {n['leader']} · sous leur plus bas 60 j : {n['cassure_bas']} · "
          f"signaux suivis : {len(suivis)} · {len(signaux)} nouveau(x) signal(aux)")
    sauver_etat(etat)


if __name__ == "__main__":
    main()
