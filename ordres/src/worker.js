// ==============================================================================
//  RADAR ORDRES — passe sur Zoomex l'ordre d'une alerte du Radar Alt, en deux appuis.
//
//  L'alerte Telegram du radar porte deux boutons : « Prendre » et « Ignorer ».
//  « Prendre » demande une confirmation ; « Confirmer » envoie un ordre au marché avec
//  le SL et le TP du ticket, la quantité étant calculée pour risquer RISQUE_USDT.
//
//  Garde-fous : seul OWNER_ID peut agir ; le prix doit être encore proche de l'entrée du
//  signal (entre R_MIN et R_MAX) ; MAX_POSITIONS positions ouvertes au plus ; une seule
//  position par paire ; ORDRES_ACTIFS=false coupe tout ; un même message ne peut passer
//  qu'un seul ordre (orderLinkId).
//
//  Commandes (envoyées au bot par le propriétaire) : /test (faux signal pour essayer les
//  boutons), /etat (mode et positions ouvertes).
//
//  Installation et réglages : voir ordres/README.md.
// ==============================================================================
const TESTNET = "https://openapi-testnet.zoomex.com";
const FRAIS_TAKER = 0.0006;
const PAIRE_TEST = "DOGEUSDT";

const num = (v, d) => (Number.isFinite(parseFloat(v)) ? parseFloat(v) : d);
const base = (env) => env.ZOOMEX_BASE || TESTNET;
const estTest = (env) => base(env).includes("testnet");
const decimales = (pas) => (String(pas).split(".")[1] || "").replace(/0+$/, "").length;
const arrondir = (x, pas) => (Math.round(x / pas) * pas).toFixed(decimales(pas));
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// ---------------- Telegram ----------------
async function tg(env, methode, corps) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${methode}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(corps),
  });
  return r.json().catch(() => ({}));
}

export function boutons(etape, donnees) {
  const [, sym, sens] = donnees.split("|");
  const nom = `${sens === "L" ? "LONG" : "SHORT"} ${sym.replace(/USDT$/, "")}`;
  if (etape === "confirmer") {
    return { inline_keyboard: [[
      { text: `✅ Confirmer ${nom}`, callback_data: "c" + donnees.slice(1) },
      { text: "↩️ Annuler", callback_data: "r" + donnees.slice(1) },
    ]] };
  }
  return { inline_keyboard: [[
    { text: `✅ Prendre ${nom}`, callback_data: "p" + donnees.slice(1) },
    { text: "❌ Ignorer", callback_data: "i" },
  ]] };
}

// ---------------- Zoomex ----------------
async function hmac(secret, texte) {
  const enc = new TextEncoder();
  const cle = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", cle, enc.encode(texte));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function zoomex(env, methode, chemin, params = {}, prive = true) {
  const requete = new URLSearchParams(params).toString();
  const corps = JSON.stringify(params);
  const headers = { "content-type": "application/json" };
  if (prive) {
    const ts = String(Date.now()), fenetre = "5000";
    headers["X-BAPI-API-KEY"] = env.ZOOMEX_API_KEY;
    headers["X-BAPI-TIMESTAMP"] = ts;
    headers["X-BAPI-RECV-WINDOW"] = fenetre;
    headers["X-BAPI-SIGN-TYPE"] = "2";
    headers["X-BAPI-SIGN"] = await hmac(env.ZOOMEX_API_SECRET, ts + env.ZOOMEX_API_KEY + fenetre + (methode === "GET" ? requete : corps));
  }
  const url = base(env) + chemin + (methode === "GET" && requete ? "?" + requete : "");
  const r = await fetch(url, { method: methode, headers, body: methode === "GET" ? undefined : corps });
  const j = await r.json().catch(() => null);
  if (!j) throw new Error(`Zoomex ne répond pas correctement (HTTP ${r.status})`);
  return j;
}

async function lire(env, chemin, params, prive = false) {
  const j = await zoomex(env, "GET", chemin, params, prive);
  if (j.retCode !== 0) throw new Error(`Zoomex : ${j.retMsg} (code ${j.retCode})`);
  return j.result;
}

// ---------------- Ordre ----------------
/** Calcule l'ordre à partir du ticket et du marché. Retourne { refus } ou { ordre, ... }. */
export function preparer(env, ticket, marche) {
  let { sym, sens, entree, sl, tp } = ticket;
  const { prix, pas, qmin, tick, levMax, notionnelMin } = marche;
  const s = sens === "L" ? 1 : -1;
  if (estTest(env)) {                       // les prix du compte de test diffèrent du réel :
    const k = prix / entree;                // on garde les mêmes écarts en %, autour du prix de test
    entree = prix; sl *= k; tp *= k;
  }
  const risque = Math.abs(entree - sl);
  const r = (s * (prix - entree)) / risque;
  if (r > num(env.R_MAX, 0.3)) return { refus: `trop tard, le prix est déjà parti (${r.toFixed(1)} R depuis le signal)` };
  if (r < num(env.R_MIN, -0.5)) return { refus: `le prix est revenu trop près du SL (${r.toFixed(1)} R depuis le signal)` };
  const dist = Math.abs(prix - sl);
  const budget = num(env.RISQUE_USDT, 1);
  const qte = Math.floor(budget / (dist + 2 * FRAIS_TAKER * prix) / pas + 1e-9) * pas;
  const notionnel = qte * prix;
  if (qte < qmin || notionnel < notionnelMin) {
    const mini = Math.max(qmin, notionnelMin / prix) * (dist + 2 * FRAIS_TAKER * prix);
    return { refus: `risque de ${budget} USDT trop petit pour cette paire (minimum ≈ ${mini.toFixed(2)} USDT)` };
  }
  const levier = Math.min(Math.floor(levMax), Math.max(1, Math.ceil(notionnel / num(env.MARGE_CIBLE, 20))));
  return {
    levier, notionnel, prix, r,
    ordre: {
      category: "linear", symbol: sym, side: s === 1 ? "Buy" : "Sell", orderType: "Market",
      qty: qte.toFixed(decimales(pas)), positionIdx: 0, tpslMode: "Full",
      takeProfit: arrondir(tp, tick), stopLoss: arrondir(sl, tick),
    },
  };
}

async function executer(env, ticket, idMessage) {
  if (String(env.ORDRES_ACTIFS ?? "true") !== "true") return { refus: "les ordres sont désactivés (ORDRES_ACTIFS)" };
  const [tk, ins] = await Promise.all([
    lire(env, "/cloud/trade/v3/market/tickers", { category: "linear", symbol: ticket.sym }),
    lire(env, "/cloud/trade/v3/market/instruments-info", { category: "linear", symbol: ticket.sym }),
  ]);
  const t = tk.list?.[0], i = ins.list?.[0];
  if (!t || !i) return { refus: `paire ${ticket.sym} introuvable sur ${estTest(env) ? "le compte de test" : "Zoomex"}` };
  const marche = {
    prix: parseFloat(t.lastPrice), pas: parseFloat(i.lotSizeFilter.qtyStep), qmin: parseFloat(i.lotSizeFilter.minOrderQty),
    tick: parseFloat(i.priceFilter.tickSize), levMax: num(i.leverageFilter?.maxLeverage, 1),
    notionnelMin: num(i.lotSizeFilter.minNotionalValue, 0),
  };
  const plan = preparer(env, ticket, marche);
  if (plan.refus) return plan;
  const pos = await lire(env, "/cloud/trade/v3/position/list", { category: "linear", settleCoin: "USDT", limit: "200" }, true);
  const ouvertes = (pos.list || []).filter((p) => parseFloat(p.size) > 0);
  if (ouvertes.some((p) => p.symbol === ticket.sym)) return { refus: `une position ${ticket.sym} est déjà ouverte` };
  const max = num(env.MAX_POSITIONS, 3);
  if (ouvertes.length >= max) return { refus: `déjà ${ouvertes.length} positions ouvertes (maximum ${max})` };
  const lev = await zoomex(env, "POST", "/cloud/trade/v3/position/set-leverage",
    { category: "linear", symbol: ticket.sym, buyLeverage: String(plan.levier), sellLeverage: String(plan.levier) });
  const res = await zoomex(env, "POST", "/cloud/trade/v3/order/create", { ...plan.ordre, orderLinkId: `radar-${idMessage}` });
  if (res.retCode !== 0) return { refus: `Zoomex a refusé l'ordre : ${res.retMsg} (code ${res.retCode})`, reessayer: true };
  return { ...plan, levierRegle: lev.retCode === 0 || /not modified/i.test(lev.retMsg || "") };
}

export function lireTicket(donnees) {
  const [, sym, sens, entree, sl, tp] = donnees.split("|");
  const t = { sym, sens, entree: parseFloat(entree), sl: parseFloat(sl), tp: parseFloat(tp) };
  const ok = /^[A-Z0-9]+USDT$/.test(sym || "") && (sens === "L" || sens === "S") &&
    [t.entree, t.sl, t.tp].every((x) => x > 0) && (sens === "L" ? t.sl < t.entree && t.entree < t.tp : t.tp < t.entree && t.entree < t.sl);
  return ok ? t : null;
}

// ---------------- Mises à jour Telegram ----------------
async function surBouton(env, cq) {
  const chat = cq.message?.chat?.id, idMessage = cq.message?.message_id, donnees = cq.data || "";
  const repondre = (text, alerte = false) => tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text, show_alert: alerte });
  const clavier = (reply_markup) => tg(env, "editMessageReplyMarkup", { chat_id: chat, message_id: idMessage, reply_markup });
  const dire = (text) => tg(env, "sendMessage", { chat_id: chat, text, parse_mode: "HTML", reply_to_message_id: idMessage });
  if (String(cq.from?.id) !== String(env.OWNER_ID)) return repondre("Action réservée au propriétaire.", true);
  if (donnees === "i") {
    await clavier({ inline_keyboard: [] });
    return repondre("Signal ignoré.");
  }
  const ticket = lireTicket(donnees);
  if (!ticket) return repondre("Ticket illisible.", true);
  const nom = `${ticket.sens === "L" ? "LONG" : "SHORT"} ${ticket.sym.replace(/USDT$/, "")}`;
  if (donnees[0] === "p") {
    const ageH = (Date.now() / 1000 - (cq.message?.date || 0)) / 3600;
    if (ageH > num(env.AGE_MAX_H, 24)) {
      await clavier({ inline_keyboard: [] });
      return repondre(`Signal trop ancien (${ageH.toFixed(0)} h).`, true);
    }
    await clavier(boutons("confirmer", donnees));
    return repondre(`Confirmer ${nom} ? Risque ${num(env.RISQUE_USDT, 1)} USDT${estTest(env) ? " (compte de TEST)" : ""}.`);
  }
  if (donnees[0] === "r") {
    await clavier(boutons("prendre", donnees));
    return repondre("Annulé.");
  }
  if (donnees[0] !== "c") return repondre("Bouton inconnu.", true);
  await clavier({ inline_keyboard: [] });          // évite un deuxième appui pendant l'envoi
  await repondre(`Envoi de l'ordre ${nom}…`);
  let res;
  try {
    res = await executer(env, ticket, idMessage);
  } catch (e) {
    res = { refus: e.message, reessayer: true };
  }
  if (res.refus) {
    if (res.reessayer) await clavier(boutons("prendre", donnees));
    return dire(`❌ <b>${esc(nom)} — ordre NON passé</b>\n${esc(res.refus)}`);
  }
  const o = res.ordre;
  return dire([
    `✅ <b>${esc(nom)} — ordre passé</b>${estTest(env) ? " (compte de TEST)" : ""}`,
    `Quantité : <code>${o.qty}</code> au marché (≈ ${res.prix})`,
    `SL : <code>${o.stopLoss}</code>`,
    `TP : <code>${o.takeProfit}</code>`,
    `Valeur ≈ ${res.notionnel.toFixed(2)} USDT · levier x${res.levier}${res.levierRegle ? "" : " (levier non modifié : vérifie-le sur Zoomex)"}`,
    "Vérifie la position dans Zoomex.",
  ].join("\n"));
}

async function surMessage(env, m) {
  if (String(m.from?.id) !== String(env.OWNER_ID)) return;
  const texte = (m.text || "").trim().split(/\s|@/)[0];
  const dire = (text, reply_markup) => tg(env, "sendMessage", { chat_id: m.chat.id, text, parse_mode: "HTML", reply_markup });
  const mode = estTest(env) ? "compte de TEST" : "compte RÉEL";
  if (texte === "/test") {
    const tk = await lire(env, "/cloud/trade/v3/market/tickers", { category: "linear", symbol: PAIRE_TEST });
    const px = parseFloat(tk.list[0].lastPrice);
    const donnees = `p|${PAIRE_TEST}|L|${px}|${(px * 0.97).toPrecision(6)}|${(px * 1.09).toPrecision(6)}`;
    return dire(`🧪 <b>Faux signal d'essai — LONG ${PAIRE_TEST.replace("USDT", "")}</b>\nMode : ${mode}. « Prendre » puis « Confirmer » passe un vrai ordre sur ce compte.`, boutons("prendre", donnees));
  }
  if (texte === "/etat") {
    const pos = await lire(env, "/cloud/trade/v3/position/list", { category: "linear", settleCoin: "USDT", limit: "200" }, true);
    const ouvertes = (pos.list || []).filter((p) => parseFloat(p.size) > 0);
    const lignes = ouvertes.map((p) => `${p.side === "Buy" ? "🟢 LONG" : "🔴 SHORT"} ${esc(p.symbol)} · ${p.size} · PnL ${p.unrealisedPnl}`);
    return dire([`Mode : ${mode} · ordres ${String(env.ORDRES_ACTIFS ?? "true") === "true" ? "actifs" : "désactivés"}`,
      `Risque par ordre : ${num(env.RISQUE_USDT, 1)} USDT · positions : ${ouvertes.length}/${num(env.MAX_POSITIONS, 3)}`, ...lignes].join("\n"));
  }
  if (texte === "/start" || texte === "/aide") return dire(`Radar Ordres (${mode}). Commandes : /test, /etat.`);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET") return new Response(`radar-ordres ok (${estTest(env) ? "test" : "reel"})`);
    if (request.method !== "POST" || url.pathname !== "/telegram") return new Response("introuvable", { status: 404 });
    if (!env.WEBHOOK_SECRET || request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("interdit", { status: 403 });
    }
    const maj = await request.json().catch(() => ({}));
    const travail = (async () => {
      try {
        if (maj.callback_query) await surBouton(env, maj.callback_query);
        else if (maj.message) await surMessage(env, maj.message);
      } catch (e) {
        console.error("radar-ordres", e);
        const chat = maj.callback_query?.message?.chat?.id ?? maj.message?.chat?.id;
        if (chat) await tg(env, "sendMessage", { chat_id: chat, text: `❌ Erreur : ${e.message}` });
      }
    })();
    if (ctx?.waitUntil) ctx.waitUntil(travail); else await travail;
    return new Response("ok");                      // toujours 200 : Telegram ne doit pas renvoyer la mise à jour
  },
};
