# ==============================================================================
#  MÉTÉO ALTS V1.1 — un message Telegram par jour ou à la demande, SANS signal d'entrée
#
#  But : te dire OÙ regarder et dans quel contexte, pas QUAND entrer.
#  Basé sur ce que les backtests ont montré (4 ans, 97 paires) :
#    - acheter une alt qui clôture au plus haut de 50 jours fait mieux qu'acheter au hasard,
#      surtout quand BTC est au-dessus de sa moyenne 200 jours ;
#    - acheter les alts qui ont le plus monté sur 30 jours ne marche PAS ;
#    - les stops plus serrés que le mouvement normal d'une journée se font sortir par le bruit.
#
#  Contenu du message (bougies journalières clôturées, UTC) :
#    1. BTC : au-dessus ou en dessous de sa moyenne 200 jours, variation 7 jours.
#    2. Largeur du marché : part des alts liquides au-dessus de leur moyenne 50 jours.
#    3. Feu : 🟢 favorable aux longs / 🟠 mitigé / 🔴 défavorable.
#    4. 🚀 Nouveaux plus hauts de 50 jours (clôture d'hier).
#    5. 💪 Alts solides : au-dessus de leurs moyennes 50 et 200 jours, à moins de 5 % du plus haut.
#    6. ⛔ À éviter en long : nouveaux plus bas de 50 jours.
#    Pour chaque alt : le « bruit » = mouvement moyen d'une journée (ATR 20 jours, en %).
#
#  Paires retenues : volume moyen 30 jours >= LIQ_MIN USDT par jour.
#  Lancement : GitHub Actions, une fois par jour (.github/workflows/meteo.yml).
#  V1.1 : MÉTÉO À LA DEMANDE. Écris « meteo » sur Telegram : elle arrive au prochain scan de
#         Crypto Pépite (toutes les 30 minutes, de 7 h à 23 h). Le scan lance pour cela
#         « python meteo.py --si-demande » juste avant crypto_pepite.py, qui marque ensuite
#         les messages comme lus (pas de double envoi). Les demandes de plus de 2 h sont ignorées.
#  Secrets utilisés : TELEGRAM_TOKEN et TELEGRAM_CHAT_ID (les mêmes que Crypto Pépite).
# ==============================================================================
import json, os, re, sys, time
from datetime import datetime, timezone
from html import escape, unescape

import numpy as np
import pandas as pd
import requests

VERSION = "1.1"

LIQ_MIN      = 10_000_000   # volume moyen 30 jours minimum (USDT par jour)
PAIRES_MAX   = 150          # nb max de paires examinées (les plus liquides aujourd'hui)
N_HAUT       = 50           # plus haut / plus bas de 50 jours (en clôture)
PRES_DU_HAUT = 0.05         # « solide » : à moins de 5 % du plus haut de 50 jours
LARGEUR_OK   = 50           # % d'alts au-dessus de leur moyenne 50 j pour un marché « large »
MAX_LISTE    = 8            # nb max de paires par rubrique

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

JOUR = 86_400_000
SOURCES = {"Zoomex": "https://openapi.zoomex.com/cloud/trade/v3/market/",
           "Bybit":  "https://api.bybit.com/v5/market/"}
SRC = None
SESS = requests.Session()
JOURS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


# ---------------- DONNÉES ----------------
def api(path, **params):
    for essai in range(4):
        try:
            r = SESS.get(SOURCES[SRC] + path, params=params, timeout=20)
            if r.status_code in (403, 451):
                return None
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
            return True
    return False


def liste_paires():
    res = api("tickers", category="linear")
    df = pd.DataFrame(res["list"])
    df["turnover24h"] = pd.to_numeric(df["turnover24h"], errors="coerce")
    df = df[df.symbol.str.endswith("USDT")].sort_values("turnover24h", ascending=False)
    syms = list(df.symbol.head(PAIRES_MAX))
    return syms if "BTCUSDT" in syms else ["BTCUSDT"] + syms


def bougies_jour(sym, maintenant):
    res = api("kline", category="linear", symbol=sym, interval="D", limit=260)
    if not isinstance(res, dict) or not res.get("list"):
        return None
    df = pd.DataFrame(res["list"])
    df = df.iloc[:, :7] if df.shape[1] >= 7 else df.iloc[:, :6].assign(x=np.nan)
    df.columns = ["t", "o", "h", "l", "c", "v", "to"]
    df = df.astype(float).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    if df["to"].isna().all():
        df["to"] = df.v * df.c
    return df[df.t + JOUR <= maintenant].reset_index(drop=True)     # bougies clôturées uniquement


# ---------------- CALCULS ----------------
def fiche(sym, df):
    """Les chiffres utiles d'une paire, à la dernière clôture journalière."""
    if df is None or len(df) < N_HAUT + 21:
        return None
    c = df.c
    dernier = float(c.iloc[-1])
    prec = c.shift(1)
    tr = pd.concat([df.h - df.l, (df.h - prec).abs(), (df.l - prec).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().iloc[-1])
    avant = c.iloc[-1 - N_HAUT:-1]                                  # les 50 clôtures précédentes
    m200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else np.nan
    return dict(symbol=sym, c=dernier, t=float(df.t.iloc[-1]),
                m50=float(c.rolling(50).mean().iloc[-1]), m200=m200,
                haut=float(avant.max()), bas=float(avant.min()),
                bruit=100 * atr / dernier,
                j1=100 * (dernier / float(c.iloc[-2]) - 1),
                j7=100 * (dernier / float(c.iloc[-8]) - 1),
                liq=float(df.to.tail(30).mean()))


def classer(fiches):
    """Range les alts liquides en trois rubriques et calcule la largeur du marché."""
    alts = [f for f in fiches if f["symbol"] != "BTCUSDT" and f["liq"] >= LIQ_MIN and f["bruit"] >= 0.5]
    if not alts:
        return [], [], [], np.nan, 0
    largeur = 100 * np.mean([f["c"] > f["m50"] for f in alts])
    hauts = sorted([f for f in alts if f["c"] > f["haut"]], key=lambda f: -f["liq"])
    bas = sorted([f for f in alts if f["c"] < f["bas"]], key=lambda f: -f["liq"])
    solides = [f for f in alts
               if f["c"] <= f["haut"] and f["c"] >= (1 - PRES_DU_HAUT) * f["haut"]
               and f["c"] > f["m50"] and (np.isnan(f["m200"]) or f["c"] > f["m200"])]
    solides.sort(key=lambda f: f["haut"] / f["c"])                  # les plus proches du plus haut d'abord
    return hauts, solides, bas, largeur, len(alts)


# ---------------- MESSAGE ----------------
def nom(f):
    return f["symbol"][:-4]


def ligne(f, ecart=False):
    txt = f"<b>{escape(nom(f))}</b> · hier {f['j1']:+.1f} % · bruit {f['bruit']:.0f} %"
    if ecart:
        txt += f" · à {100 * (f['haut'] / f['c'] - 1):.1f} % du plus haut"
    return txt


def message(btc, hauts, solides, bas, largeur, n_alts):
    d = datetime.fromtimestamp(btc["t"] / 1000 + 86_400, timezone.utc)   # la bougie d'hier ferme aujourd'hui 0 h UTC
    date = f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]}"
    fond = not np.isnan(btc["m200"]) and btc["c"] > btc["m200"]
    large = largeur >= LARGEUR_OK
    if fond and large:
        feu = "🟢 <b>Contexte favorable aux longs</b>"
    elif fond or large:
        feu = "🟠 <b>Contexte mitigé</b> : longs possibles, taille réduite"
    else:
        feu = "🔴 <b>Contexte défavorable aux longs</b> : mieux vaut ne rien faire"
    ecart200 = "" if np.isnan(btc["m200"]) else f" ({100 * (btc['c'] / btc['m200'] - 1):+.0f} %)"
    out = [f"🌤 <b>MÉTÉO ALTS — {date}</b>",
           "",
           f"₿ BTC {btc['c']:,.0f} · {'au-dessus' if fond else 'en dessous'} de sa moyenne 200 j{ecart200} · "
           f"7 j {btc['j7']:+.1f} %".replace(",", " "),
           f"📊 {largeur:.0f} % des {n_alts} alts liquides au-dessus de leur moyenne 50 j",
           feu, ""]

    out.append(f"🚀 <b>Nouveaux plus hauts de {N_HAUT} jours</b> ({len(hauts)})")
    out += [ligne(f) for f in hauts[:MAX_LISTE]] or ["aucun"]
    if len(hauts) > MAX_LISTE:
        out.append(f"… et {len(hauts) - MAX_LISTE} autres")
    out.append("")
    out.append(f"💪 <b>Alts solides, près de leur plus haut</b> ({len(solides)})")
    out += [ligne(f, ecart=True) for f in solides[:MAX_LISTE]] or ["aucune"]
    out.append("")
    out.append(f"⛔ <b>À éviter en long : nouveaux plus bas de {N_HAUT} jours</b> ({len(bas)})")
    out.append(", ".join(escape(nom(f)) for f in bas[:12]) or "aucun")
    out += ["",
            "<i>Bruit = mouvement moyen d'une journée. Un stop plus serré que ça se fait sortir par le hasard.</i>",
            f"<i>Ce message n'est pas un signal d'entrée. News / macro non vérifiées. V{VERSION}</i>"]
    return "\n".join(out)


def telegram(texte):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("(Telegram non configuré : message non envoyé)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = dict(chat_id=TELEGRAM_CHAT_ID, text=texte, parse_mode="HTML", disable_web_page_preview=True)
    try:
        r = requests.post(url, data=data, timeout=15)
        if r.status_code == 400:                                    # mise en forme refusée -> texte simple
            data.pop("parse_mode")
            data["text"] = unescape(re.sub(r"<[^>]+>", "", texte))
            r = requests.post(url, data=data, timeout=15)
        print("Telegram :", "envoyé" if r.ok else f"échec ({r.status_code})")
    except Exception as e:
        print(f"Telegram : échec ({e})")


def demandee():
    """Vrai si tu as écrit « meteo » (ou « météo ») sur Telegram depuis le dernier scan.
    Les messages ne sont PAS marqués comme lus ici : crypto_pepite.py le fait juste après."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                         params=dict(timeout=0, allowed_updates=json.dumps(["message", "channel_post"])),
                         timeout=15)
        maj = r.json().get("result") or []
    except Exception:
        return False
    for u in maj:
        m = u.get("message") or u.get("channel_post") or {}
        if str(m.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
            continue                                              # uniquement ta conversation
        if time.time() - float(m.get("date", 0)) > 7200:
            continue                                              # demande trop ancienne
        mots = (m.get("text") or "").strip().lower().split()
        if mots and mots[0].strip("/.,!?:").startswith(("meteo", "météo")):
            return True
    return False


def main():
    print(f"MÉTÉO ALTS V{VERSION}")
    if "--si-demande" in sys.argv and not demandee():
        print("Pas de demande de météo sur Telegram.")
        return
    if not choisir_source():
        telegram("⚠️ MÉTÉO ALTS : données de marché inaccessibles ce matin.")
        sys.exit(1)
    maintenant = int(time.time() * 1000)
    fiches = []
    for sym in liste_paires():
        f = fiche(sym, bougies_jour(sym, maintenant))
        if f:
            fiches.append(f)
        time.sleep(0.08)
    btc = next((f for f in fiches if f["symbol"] == "BTCUSDT"), None)
    if btc is None:
        telegram("⚠️ MÉTÉO ALTS : données BTC indisponibles ce matin.")
        sys.exit(1)
    # on ne garde que les paires dont la dernière bougie est bien celle d'hier
    fiches = [f for f in fiches if f["t"] == btc["t"]]
    texte = message(btc, *classer(fiches))
    print(unescape(re.sub(r"<[^>]+>", "", texte)))
    telegram(texte)


if __name__ == "__main__":
    main()
