# ==============================================================================
#  RADAR ALT V1.0 — repère les PRÉ-SETUPS haussiers sur les altcoins (Zoomex, USDT perp)
#
#  Philosophie : la machine REPÈRE et PRÉVIENT TÔT, c'est TOI qui décides
#  (entrer / attendre / trop tard). Aucune promesse de gain : les backtests ont montré
#  qu'aucun setup mécanique simple ne bat les frais à lui seul.
#
#  Deux familles, LONG uniquement, repérées en H4 :
#   📈 CONTINUATION : alt en tendance haussière (H4 et journalier), qui fait une pause
#      calme après un plus haut récent, en restant au-dessus de sa moyenne 50 H4.
#      Déclenchement = reprise du plus haut de l'impulsion.
#      Invalidation = sous le plus bas de la pause.
#   🔄 RETOURNEMENT : alt qui a beaucoup baissé, puis fait un creux PLUS HAUT que le
#      précédent (double creux / « W »). Déclenchement = reprise du sommet du rebond.
#      Invalidation = sous le dernier creux.
#
#  Cycle de vie d'un pré-setup :
#   👀 En formation  -> 🎯 Prêt (prix à moins de PRET_ATR ATR H4 du déclenchement)
#   -> 🚀 Déclenché (clôture H1 au-dessus du niveau) -> ⌛ Trop tard (prix parti à plus de
#   TROP_TARD_ATR ATR H4 au-dessus) ou ❌ Invalidé (clôture H1 sous l'invalidation).
#
#  Messages Telegram :
#   - un RÉSUMÉ toutes les 4 h, juste après la clôture H4 (sauf la nuit, voir SILENCE_NUIT) ;
#   - une ALERTE immédiate à chaque déclenchement, avec le ticket copiable.
#
#  Suivi automatique : chaque déclenchement est suivi (objectif 2 R, SL, 72 h max) et
#  enregistré dans radar_journal.csv, pour mesurer ce que valent les alertes brutes.
#
#  Fichiers : radar_etat.json (pré-setups en cours), radar_journal.csv (déclenchements).
#  Lancement : .github/workflows/radar.yml, toutes les heures (cron-job.org, minute 2).
#  Secrets : TELEGRAM_TOKEN et TELEGRAM_CHAT_ID (les mêmes que Crypto Pépite).
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

VERSION = "1.0"

# ---------------- RÉGLAGES ----------------
LIQ_MIN        = 10_000_000   # volume 24 h minimum (USDT)
PAIRES_MAX     = 100          # paires examinées (les plus liquides)
PRET_ATR       = 1.0          # « prêt » : prix à moins de 1 ATR H4 du déclenchement
FORMATION_ATR  = 4.0          # au-delà de 4 ATR H4 du déclenchement : ignoré
TROP_TARD_ATR  = 1.0          # « trop tard » : prix à plus de 1 ATR H4 au-dessus du déclenchement
MARGE_SL_ATR   = 0.3          # marge sous l'invalidation, en ATR H4
OBJECTIF_R     = 2.0          # objectif indicatif
SUIVI_MAX_H    = 72           # suivi d'un déclenchement : 72 h maximum
SILENCE_NUIT   = (23, 7)      # pas de résumé entre 23 h et 7 h (heure de Paris) ; alertes maintenues
RISQUE         = 1.0          # USDT risqués par trade (pour le ticket)
MARGE_CIBLE    = 20.0         # marge max souhaitée par trade (USDT)
FRAIS_TAKER    = 0.0006
MAX_LISTE      = 8

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
    duree = {"60": H1, "240": H4, "D": JOUR}[iv]
    return df[df.t + duree <= maintenant].reset_index(drop=True)


def univers():
    res = api("tickers", category="linear")
    if not res:
        return [], {}
    df = pd.DataFrame(res["list"])
    for c in ["turnover24h", "lastPrice"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df.symbol.str.endswith("USDT") & (df.turnover24h >= LIQ_MIN)]
    df = df.sort_values("turnover24h", ascending=False).head(PAIRES_MAX)
    return list(df.symbol), dict(zip(df.symbol, df.lastPrice))


def instruments():
    res = api("instruments-info", category="linear", limit=1000)
    info = {}
    for it in (res or {}).get("list", []):
        try:
            info[it["symbol"]] = dict(tick=float(it["priceFilter"]["tickSize"]),
                                      step=float(it["lotSizeFilter"]["qtyStep"]),
                                      minq=float(it["lotSizeFilter"]["minOrderQty"]))
        except Exception:
            pass
    return info


# ---------------- INDICATEURS ----------------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df.c.shift()
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ---------------- DÉTECTION (H4) ----------------
def continuation(h4, d):
    """Tendance haussière H4 + journalier, pause calme après un plus haut récent."""
    if len(h4) < 80 or d is None or len(d) < 60:
        return None
    c, a = h4.c, float(atr(h4).iloc[-1])
    e20, e50 = ema(c, 20), ema(c, 50)
    if not (c.iloc[-1] > e50.iloc[-1] and e20.iloc[-1] > e50.iloc[-1] and e50.iloc[-1] > e50.iloc[-7]):
        return None
    if not d.c.iloc[-1] > ema(d.c, 50).iloc[-1]:
        return None                                         # trend is your friend : journalier aussi
    fen = h4.tail(30).reset_index(drop=True)
    i_haut = int(fen.h.idxmax())
    age = len(fen) - 1 - i_haut                             # bougies depuis le plus haut
    if not 3 <= age <= 20:
        return None                                         # pas encore de pause, ou pause trop vieille
    haut = float(fen.h.iloc[i_haut])
    pause = fen.iloc[i_haut + 1:]
    bas = float(pause.l.min())
    repli = (haut - bas) / a
    if not 1.0 <= repli <= 4.0:
        return None                                         # repli trop faible ou trop profond
    if (pause.c < e50.tail(len(pause)).values).any():
        return None                                         # la pause a clôturé sous la moyenne 50 H4
    calme = float((pause.h - pause.l).tail(4).mean()) < 0.8 * a
    return dict(type="continuation", declenchement=haut, invalidation=bas - MARGE_SL_ATR * a,
                atr=a, info=dict(repli_atr=round(repli, 1), age_h4=age, calme=bool(calme)))


def retournement(h4):
    """Forte baisse, creux L1, rebond B, creux plus haut L2 : reprise de B attendue."""
    if len(h4) < 80:
        return None
    a = float(atr(h4).iloc[-1])
    fen = h4.tail(40).reset_index(drop=True)
    n = len(fen)
    i1 = int(fen.l.iloc[:-2].idxmin())
    if not 6 <= n - 1 - i1 <= 38:
        return None
    l1 = float(fen.l.iloc[i1])
    pos = len(h4) - 40 + i1                                 # position du creux dans tout l'historique
    avant = h4.iloc[max(0, pos - 30):pos]
    if len(avant) == 0 or float(avant.h.max()) < l1 + 4 * a:
        return None                                         # pas de vraie baisse avant le creux
    apres = fen.iloc[i1 + 1:]
    i_b = int(apres.h.idxmax())
    b = float(fen.h.iloc[i_b])
    if b < l1 + 1.5 * a:
        return None                                         # rebond trop faible
    suite = fen.iloc[i_b + 1:]
    if len(suite) < 2:
        return None
    i2 = int(suite.l.idxmin())
    l2 = float(fen.l.iloc[i2])
    if not (l2 > l1 + 0.3 * a and n - 1 - i2 >= 1):
        return None                                         # pas de creux plus haut (encore)
    if float(fen.c.iloc[-1]) >= b:
        return None                                         # déjà au-dessus en H4 : ce n'est plus un pré-setup
    return dict(type="retournement", declenchement=b, invalidation=l2 - MARGE_SL_ATR * a,
                atr=a, info=dict(creux1=l1, creux2=l2, baisse_atr=round((float(avant.h.max()) - l1) / a, 1)))


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
            return json.load(f)
    except Exception:
        return dict(setups={}, dernier_resume=0)


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
    """Suit un déclenchement sur les bougies H1 : objectif 2 R, SL, ou 72 h max."""
    b = h1[h1.t >= s["t_decl"]]
    e, sl, tp = s["entree"], s["sl"], s["objectif"]
    risque = e - sl
    mfe = 0.0
    for _, x in b.iterrows():
        if x.l <= sl:
            return "SL", -1.0, max(mfe, 0), (x.t + H1 - s["t_decl"]) / H1
        mfe = max(mfe, (x.h - e) / risque)
        if x.h >= tp:
            return "OBJECTIF", OBJECTIF_R, mfe, (x.t + H1 - s["t_decl"]) / H1
    if len(b) and (b.t.iloc[-1] + H1 - s["t_decl"]) / H1 >= SUIVI_MAX_H:
        return "EXPIRE", (float(b.c.iloc[-1]) - e) / risque, mfe, SUIVI_MAX_H
    return None, None, mfe, None


# ---------------- MESSAGES ----------------
NOMS = {"continuation": "📈 Continuation", "retournement": "🔄 Retournement"}


def ligne_setup(s, px):
    a, t = s["atr"], s["tick"]
    dist = (s["declenchement"] - px) / a
    pct = 100 * (s["declenchement"] / px - 1)
    sl_pct = 100 * (1 - s["invalidation"] / s["declenchement"])
    return (f"<b>{escape(s['sym'][:-4])}</b> {NOMS[s['type']]} · déclenchement {escape(fmt(arrondi(s['declenchement'], t), t))} "
            f"({pct:+.1f} %, {dist:.1f} ATR) · SL −{sl_pct:.1f} % · bruit {s['bruit']:.0f} %")


def resume(etat, prix, ctx, nouveaux_decl):
    maintenant = datetime.now(PARIS)
    actifs = [s for s in etat["setups"].values() if s["etape"] in ("pret", "formation")]
    prets = sorted([s for s in actifs if s["etape"] == "pret"],
                   key=lambda s: (s["declenchement"] - prix.get(s["sym"], s["declenchement"])) / s["atr"])
    form = sorted([s for s in actifs if s["etape"] == "formation"],
                  key=lambda s: (s["declenchement"] - prix.get(s["sym"], s["declenchement"])) / s["atr"])
    recents = [s for s in etat["setups"].values()
               if s["etape"] in ("declenche", "trop_tard") and time.time() * 1000 - s["t_decl"] < 4 * H1 * 1.05]
    out = [f"📡 <b>RADAR ALT — {maintenant:%d/%m %H:%M}</b>", "", escape(ctx["texte"]), ""]
    out.append(f"🎯 <b>Prêts</b> (à moins de {PRET_ATR:g} ATR du déclenchement) : {len(prets)}")
    out += [ligne_setup(s, prix.get(s["sym"], s["declenchement"])) for s in prets[:MAX_LISTE]] or ["aucun"]
    out.append("")
    out.append(f"👀 <b>En formation</b> : {len(form)}")
    out += [ligne_setup(s, prix.get(s["sym"], s["declenchement"])) for s in form[:MAX_LISTE]] or ["aucun"]
    if len(form) > MAX_LISTE:
        out.append(f"… et {len(form) - MAX_LISTE} autres")
    if recents:
        out += ["", "🚀 <b>Déclenchés ces 4 dernières heures</b>"]
        for s in recents:
            px = prix.get(s["sym"], s["entree"])
            ecart = (px - s["declenchement"]) / s["atr"]
            etat_txt = "⌛ trop tard" if s["etape"] == "trop_tard" else "encore jouable"
            if ecart < 0:
                etat_txt = "retombé sous le niveau"
            out.append(f"<b>{escape(s['sym'][:-4])}</b> {NOMS[s['type']]} · {ecart:+.1f} ATR par rapport au niveau · {etat_txt}")
    out += ["", "<i>Pré-setups H4, LONG uniquement. Ce n'est pas un signal d'entrée : c'est toi qui décides. "
                f"News / macro non vérifiées. V{VERSION}</i>"]
    return "\n".join(out)


def alerte(s, px, ctx, inf):
    t, step = inf.get("tick"), inf.get("step")
    e, sl = arrondi(px, t), arrondi(s["invalidation"], t)
    tp = arrondi(e + OBJECTIF_R * (e - sl), t)
    sz = sizing(e, sl, inf)
    frais = 2 * FRAIS_TAKER * e / (e - sl)
    ecart = (px - s["declenchement"]) / s["atr"]
    base = escape(s["sym"][:-4])
    i = s.get("info", {})
    if s["type"] == "continuation":
        pourquoi = (f"Pause de {i.get('age_h4')} bougies H4 après un plus haut, repli de {i.get('repli_atr')} ATR, "
                    f"tenue au-dessus de la moyenne 50 H4" + (" · pause calme ✅" if i.get("calme") else ""))
    else:
        pourquoi = (f"Baisse de {i.get('baisse_atr')} ATR, puis creux plus haut "
                    f"({escape(fmt(arrondi(i.get('creux2', 0), t), t))} > {escape(fmt(arrondi(i.get('creux1', 0), t), t))})")
    verdict = ("✅ prix encore proche du niveau" if ecart <= 0.5 else
               "⚠️ déjà un peu parti : attendre un repli ?" if ecart <= TROP_TARD_ATR else "⌛ probablement trop tard")
    lignes = [
        f"🚀 <b>RADAR ALT — {base} — DÉCLENCHÉ</b> {ctx['feu']}",
        f"{NOMS[s['type']]} · clôture H1 au-dessus de {escape(fmt(arrondi(s['declenchement'], t), t))}",
        f"<i>{escape(pourquoi)}</i>",
        f"{verdict} ({ecart:+.1f} ATR H4 au-dessus du niveau)",
        "",
        f"Paire : <code>{base}</code>",
        f"Quantité : <code>{fmt(sz['q'], step)}</code> {base}",
        f"Entrée : <code>{fmt(e, t)}</code>",
        f"SL : <code>{fmt(sl, t)}</code>",
        f"TP ({OBJECTIF_R:g} R, indicatif) : <code>{fmt(tp, t)}</code>",
        f"Valeur : <code>{sz['notional']:.2f}</code> USDT · levier x{sz['lev']} · marge ≈ {sz['marge']:.2f} USDT",
        f"Frais ≈ {frais:.2f} R · SL à {100 * (1 - sl / e):.1f} % (bruit journalier {s['bruit']:.0f} %)"
        + (" ⚠️ SL plus serré que le bruit d'une journée" if 100 * (1 - sl / e) < 0.5 * s["bruit"] else ""),
        "",
        escape(ctx["texte"]),
        "⚠️ News / macro non vérifiées",
        f"📊 <a href=\"{escape(lien_tv(s['sym']))}\">Graphique TradingView H4</a>",
    ]
    if sz["trop_petit"]:
        lignes.insert(5, "⚠️ Quantité sous le minimum Zoomex")
    return "\n".join(lignes)


# ---------------- PROGRAMME ----------------
def main():
    print(f"RADAR ALT V{VERSION} — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    maintenant = int(time.time() * 1000)
    syms, prix_tk = univers()
    if not syms:
        print("⛔ Données Zoomex inaccessibles.")
        sys.exit(1)
    info = instruments()
    etat = charger_etat()

    # 1) Analyse des paires
    trouves, h1s, quotidiens = {}, {}, []
    for sym in syms:
        d = bougies(sym, "D", 80, maintenant)
        quotidiens.append(d)
        if sym == "BTCUSDT":
            continue
        h4 = bougies(sym, "240", 200, maintenant)
        h1 = bougies(sym, "60", 100, maintenant)
        if h4 is None or h1 is None or len(h1) < 10:
            continue
        h1s[sym] = h1
        bruit = float(100 * atr(d, 20).iloc[-1] / d.c.iloc[-1]) if d is not None and len(d) > 25 else np.nan
        for fn in (lambda: continuation(h4, d), lambda: retournement(h4)):
            s = fn()
            if not s:
                continue
            sid = f"{sym}|{s['type']}|{fmt(arrondi(s['declenchement'], info.get(sym, {}).get('tick')))}"
            trouves[sid] = dict(s, id=sid, sym=sym, bruit=bruit, tick=info.get(sym, {}).get("tick"))
        time.sleep(0.05)
    prix = {s: float(h1s[s].c.iloc[-1]) for s in h1s}
    prix.update({s: p for s, p in prix_tk.items() if s not in prix})
    ctx = contexte(maintenant, quotidiens)
    print(ctx["texte"])

    # 2) Mise à jour du cycle de vie
    setups = etat["setups"]
    for sid, s in trouves.items():                         # nouveaux ou toujours valables
        if sid not in setups:
            setups[sid] = dict(s, etape="formation", vu=maintenant, t_decl=0)
        else:
            garde = {k: setups[sid][k] for k in ("etape", "vu", "t_decl") if k in setups[sid]}
            setups[sid] = dict(setups[sid], **{k: v for k, v in s.items() if k not in garde})
    declenches = []
    for sid, s in list(setups.items()):
        h1 = h1s.get(s["sym"])
        if h1 is None:
            continue
        c = float(h1.c.iloc[-1])
        if s["etape"] in ("formation", "pret"):
            if c < s["invalidation"]:
                s["etape"] = "invalide"
            elif c > s["declenchement"]:
                inf = info.get(s["sym"], {})
                e = arrondi(c, inf.get("tick"))
                sl = arrondi(s["invalidation"], inf.get("tick"))
                s.update(etape="declenche", t_decl=float(h1.t.iloc[-1]) + H1, entree=e, sl=sl,
                         objectif=e + OBJECTIF_R * (e - sl), feu=ctx["feu"],
                         date_decl=datetime.fromtimestamp((float(h1.t.iloc[-1]) + H1) / 1000, PARIS).strftime("%Y-%m-%d %H:%M"))
                declenches.append(s)
            elif sid not in trouves:
                s["etape"] = "disparu"                      # le pré-setup ne correspond plus aux règles
            elif (s["declenchement"] - c) / s["atr"] <= PRET_ATR:
                s["etape"] = "pret"
            elif (s["declenchement"] - c) / s["atr"] > FORMATION_ATR:
                s["etape"] = "disparu"
            else:
                s["etape"] = "formation"
        if s["etape"] in ("declenche", "trop_tard"):
            if s["etape"] == "declenche" and (c - s["declenchement"]) / s["atr"] > TROP_TARD_ATR:
                s["etape"] = "trop_tard"
            statut, r, mfe, duree = suivre(s, h1)
            if statut:
                journaliser(s, statut, r, mfe, duree)
                s["etape"] = "termine"
    # ménage : on oublie les setups terminés, invalidés ou disparus depuis plus de 2 jours
    for sid in [k for k, s in setups.items()
                if s["etape"] in ("termine", "invalide", "disparu") and maintenant - s.get("vu", 0) > 2 * JOUR]:
        del setups[sid]
    for s in setups.values():
        if s["etape"] in ("formation", "pret"):
            s["vu"] = maintenant

    # 3) Messages
    for s in declenches:
        print(f"Déclenché : {s['sym']} {s['type']}")
        telegram(alerte(s, prix.get(s["sym"], s["declenchement"]), ctx, info.get(s["sym"], {})))
    heure_paris = datetime.now(PARIS).hour
    nuit = SILENCE_NUIT[0] <= heure_paris or heure_paris < SILENCE_NUIT[1]
    bloc_h4 = maintenant // H4
    forcer = "--resume" in sys.argv
    if forcer or (etat.get("dernier_resume", 0) < bloc_h4 and not nuit):
        telegram(resume(etat, prix, ctx, declenches))
        etat["dernier_resume"] = bloc_h4
    n = {e: sum(1 for s in setups.values() if s["etape"] == e) for e in ("formation", "pret", "declenche", "trop_tard")}
    print(f"Pré-setups : {n['formation']} en formation · {n['pret']} prêts · {n['declenche']} déclenchés suivis · "
          f"{n['trop_tard']} trop tard · {len(declenches)} nouveau(x) déclenchement(s)")
    sauver_etat(etat)


if __name__ == "__main__":
    main()
