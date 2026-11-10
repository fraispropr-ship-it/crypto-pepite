import test from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import worker, { preparer, lireTicket, boutons, zoomex } from "../src/worker.js";

const ENV = { TELEGRAM_TOKEN: "T", OWNER_ID: "42", WEBHOOK_SECRET: "s3", ZOOMEX_API_KEY: "KEY", ZOOMEX_API_SECRET: "SECRET",
  ZOOMEX_BASE: "https://openapi.zoomex.com", RISQUE_USDT: "1", MARGE_CIBLE: "20", MAX_POSITIONS: "3" };
const MARCHE = { prix: 0.83, pas: 0.1, qmin: 0.1, tick: 0.0001, levMax: 75, notionnelMin: 5 };
const DONNEES = "c|DOTUSDT|S|0.8316|0.8752|0.7008";

function faux({ prix = "0.8300", positions = [], ordre = { retCode: 0, retMsg: "OK", result: { orderId: "1" } } } = {}) {
  const appels = [];
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url), corps = init.body ? JSON.parse(init.body) : null;
    appels.push({ u, corps, headers: init.headers || {}, brut: init.body });
    let j = { ok: true };
    if (u.includes("/market/tickers")) j = { retCode: 0, result: { list: [{ lastPrice: prix }] } };
    else if (u.includes("/instruments-info")) j = { retCode: 0, result: { list: [{ lotSizeFilter: { qtyStep: "0.1", minOrderQty: "0.1", minNotionalValue: "5" }, priceFilter: { tickSize: "0.0001" }, leverageFilter: { maxLeverage: "75.00" } }] } };
    else if (u.includes("/position/list")) j = { retCode: 0, result: { list: positions } };
    else if (u.includes("/set-leverage")) j = { retCode: 0, retMsg: "OK" };
    else if (u.includes("/order/create")) j = ordre;
    return { status: 200, json: async () => j };
  };
  return appels;
}

const appui = (data, de = 42, secret = "s3") => worker.fetch(new Request("https://w/telegram", {
  method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": secret },
  body: JSON.stringify({ callback_query: { id: "q", from: { id: de }, data, message: { message_id: 7, date: Date.now() / 1000, chat: { id: 42 } } } }),
}), ENV);

test("ticket : lecture et validation", () => {
  assert.deepEqual(lireTicket(DONNEES), { sym: "DOTUSDT", sens: "S", entree: 0.8316, sl: 0.8752, tp: 0.7008 });
  assert.equal(lireTicket("c|DOTUSDT|L|0.8316|0.8752|0.7008"), null);      // SL du mauvais côté pour un long
  assert.equal(lireTicket("c|DOT;rm|S|1|2|0.5"), null);
});

test("préparation : quantité pour 1 USDT de risque, SL et TP au tick", () => {
  const p = preparer(ENV, lireTicket(DONNEES), MARCHE);
  assert.equal(p.ordre.side, "Sell");
  assert.equal(p.ordre.qty, "21.6");                    // 1 / (0.0452 + 2 × 0.0006 × 0.83) = 21.65 -> 21.6
  assert.equal(p.ordre.stopLoss, "0.8752");
  assert.equal(p.ordre.takeProfit, "0.7008");
  assert.equal(p.levier, 1);
});

test("préparation : refus si le prix est déjà parti ou revenu près du SL", () => {
  assert.match(preparer(ENV, lireTicket(DONNEES), { ...MARCHE, prix: 0.80 }).refus, /trop tard/);
  assert.match(preparer(ENV, lireTicket(DONNEES), { ...MARCHE, prix: 0.86 }).refus, /près du SL/);
});

test("préparation : refus si le risque est trop petit pour la paire", () => {
  assert.match(preparer({ ...ENV, RISQUE_USDT: "0.1" }, lireTicket(DONNEES), MARCHE).refus, /trop petit/);
});

test("préparation : sur le compte de test, mêmes écarts en % autour du prix de test", () => {
  const p = preparer({ ...ENV, ZOOMEX_BASE: "https://openapi-testnet.zoomex.com" }, lireTicket(DONNEES), { ...MARCHE, prix: 1.6632 });
  assert.equal(p.ordre.stopLoss, "1.7504");
  assert.equal(p.ordre.takeProfit, "1.4016");
});

test("signature : identique à la formule de la documentation Zoomex", async () => {
  const appels = faux();
  await zoomex(ENV, "POST", "/cloud/trade/v3/order/create", { category: "linear", symbol: "DOTUSDT" });
  const { headers, brut } = appels[0];
  const attendu = createHmac("sha256", "SECRET").update(headers["X-BAPI-TIMESTAMP"] + "KEY" + "5000" + brut).digest("hex");
  assert.equal(headers["X-BAPI-SIGN"], attendu);
  await zoomex(ENV, "GET", "/cloud/trade/v3/position/list", { category: "linear", settleCoin: "USDT" });
  const g = appels[1];
  assert.ok(g.u.endsWith("?category=linear&settleCoin=USDT"));
  assert.equal(g.headers["X-BAPI-SIGN"], createHmac("sha256", "SECRET").update(g.headers["X-BAPI-TIMESTAMP"] + "KEY5000category=linear&settleCoin=USDT").digest("hex"));
});

test("webhook : secret obligatoire, propriétaire uniquement", async () => {
  const appels = faux();
  assert.equal((await appui(DONNEES, 42, "faux")).status, 403);
  await appui(DONNEES, 99);
  assert.ok(!appels.some((a) => a.u.includes("zoomex")));
  assert.match(appels.at(-1).corps.text, /propriétaire/);
});

test("« Prendre » demande une confirmation sans passer d'ordre", async () => {
  const appels = faux();
  await appui("p" + DONNEES.slice(1));
  assert.ok(!appels.some((a) => a.u.includes("/order/create")));
  const clavier = appels.find((a) => a.u.includes("editMessageReplyMarkup")).corps.reply_markup;
  assert.equal(clavier.inline_keyboard[0][0].callback_data, DONNEES);
  assert.match(clavier.inline_keyboard[0][0].text, /Confirmer SHORT DOT/);
});

test("« Confirmer » passe l'ordre au marché avec SL, TP et identifiant unique", async () => {
  const appels = faux();
  await appui(DONNEES);
  const ordre = appels.find((a) => a.u.includes("/order/create")).corps;
  assert.deepEqual(ordre, { category: "linear", symbol: "DOTUSDT", side: "Sell", orderType: "Market", qty: "21.6",
    positionIdx: 0, tpslMode: "Full", takeProfit: "0.7008", stopLoss: "0.8752", orderLinkId: "radar-7" });
  assert.match(appels.at(-1).corps.text, /ordre passé/);
});

test("refus : position déjà ouverte, maximum atteint, ordres désactivés, refus Zoomex", async () => {
  let appels = faux({ positions: [{ symbol: "DOTUSDT", size: "5" }] });
  await appui(DONNEES);
  assert.match(appels.at(-1).corps.text, /déjà ouverte/);
  appels = faux({ positions: ["A", "B", "C"].map((s) => ({ symbol: s, size: "1" })) });
  await appui(DONNEES);
  assert.match(appels.at(-1).corps.text, /maximum 3/);
  assert.ok(!appels.some((a) => a.u.includes("/order/create")));
  appels = faux();
  ENV.ORDRES_ACTIFS = "false";
  await appui(DONNEES);
  delete ENV.ORDRES_ACTIFS;
  assert.match(appels.at(-1).corps.text, /désactivés/);
  appels = faux({ ordre: { retCode: 110007, retMsg: "ab not enough" } });
  await appui(DONNEES);
  assert.match(appels.at(-1).corps.text, /NON passé[\s\S]*ab not enough/);
  assert.match(JSON.stringify(appels.at(-2).corps), /Prendre/);            // boutons remis pour réessayer
});

test("boutons : données de 64 octets au plus", () => {
  const d = "p|1000000BABYDOGEUSDT|S|0.0000012345|0.0000013456|0.0000009876";
  for (const b of boutons("prendre", d).inline_keyboard[0]) assert.ok(Buffer.byteLength(b.callback_data) <= 64);
});
