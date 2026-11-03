"""Préalertes expérimentales M15 Zoomex. Aucun ordre, aucune promesse directionnelle.
Prix/OI/flux Zoomex uniquement. Delta récent = échantillon, jamais présenté comme CVD M15.
Les seuils sont des hypothèses à évaluer dans resistance_events.jsonl.
"""
import json
import math
import os
import time
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from html import escape

BAR = 900_000
STATE = 'resistance_state.json'
EVENTS = 'resistance_events.jsonl'
BASE = 'https://openapi.zoomex.com/cloud/trade/v3/market/'


def api(path, **params):
    req = Request(BASE + path + '?' + urlencode(params), headers={'User-Agent': 'RadarALT/1.2'})
    with urlopen(req, timeout=15) as response:
        data = json.load(response)
    if data.get('retCode') != 0:
        raise ValueError('Zoomex API: ' + str(data.get('retCode')))
    return data


def candles(rows, now):
    bars = {int(r[0]): dict(t=int(r[0]), o=float(r[1]), h=float(r[2]),
                           l=float(r[3]), c=float(r[4]), v=float(r[5])) for r in rows}
    return [b for t, b in sorted(bars.items()) if t + BAR <= now]


def detect(bars, now):
    """Historical pivots require 2 completed right bars. Last 4 bars excluded from level fit."""
    if len(bars) < 80 or now - bars[-1]['t'] - BAR > BAR:
        return None
    bars = bars[-192:]
    if any(b['t'] - a['t'] != BAR for a, b in zip(bars, bars[1:])):
        return None
    tr = [max(b['h'] - b['l'], abs(b['h'] - a['c']), abs(b['l'] - a['c']))
          for a, b in zip(bars, bars[1:])]
    atr = sum(tr[-14:]) / 14
    if not math.isfinite(atr) or atr <= 0:
        return None
    tol = .25 * atr
    pivots = [i for i in range(2, len(bars)-4)
              if bars[i]['h'] >= max(b['h'] for b in bars[i-2:i+3])]
    best = None
    for pivot in pivots:
        center = bars[pivot]['h']
        tests = []
        for i in pivots:
            if abs(bars[i]['h']-center) > tol:
                continue
            if not tests or (i-tests[-1] >= 4 and
                             min(b['l'] for b in bars[tests[-1]+1:i]) < center-.7*atr):
                tests.append(i)
        if len(tests) < 3 or tests[-1]-tests[0] < 16:
            continue
        level = sum(bars[i]['h'] for i in tests)/len(tests)
        lo, hi = level-tol, level+tol
        last = bars[-1]['c']
        # Do not announce a configuration already broken or far from resistance.
        if not lo-.8*atr <= last <= hi or any(b['c'] > hi for b in bars[tests[0]:]):
            continue
        compression = sum(tr[-4:])/4 < .85*(sum(tr[-24:-4])/20)
        rising_lows = min(b['l'] for b in bars[-4:]) > min(b['l'] for b in bars[-12:-4])+.1*atr
        if not (compression or rising_lows):
            continue
        candidate = dict(low=lo, high=hi, level=level, atr=atr, tests=len(tests),
                         first=bars[tests[0]]['t'], last_test=bars[tests[-1]]['t'],
                         compression=compression, rising_lows=rising_lows,
                         close=last, candle=bars[-1]['t'],
                         support=min(b['l'] for b in bars[-12:]))
        if best is None or candidate['tests'] > best['tests']:
            best = candidate
    return best


def flow(rows, now):
    """Observed taker flow, explicit duration; never extrapolate to missing intervals."""
    unique = {str(r['execId']): r for r in rows if r.get('execId')}
    trades = [r for r in unique.values() if r.get('side') in ('Buy', 'Sell')
              and now-BAR <= int(r['time']) <= now]
    if len(trades) < 20:
        return None
    start, end = min(int(r['time']) for r in trades), max(int(r['time']) for r in trades)
    if now-end > 60_000 or end-start < 30_000:
        return None
    buy = sum(float(r['size']) for r in trades if r['side'] == 'Buy')
    sell = sum(float(r['size']) for r in trades if r['side'] == 'Sell')
    if buy+sell <= 0:
        return None
    return dict(delta_base=buy-sell, buy_pct=100*buy/(buy+sell), seconds=(end-start)/1000,
                count=len(trades), start=start, end=end, sampled=True)


def oi_change(previous, value, now):
    if previous and 5*60_000 <= now-previous['t'] <= 45*60_000 and previous['oi'] > 0:
        return dict(pct=100*(value/previous['oi']-1), minutes=(now-previous['t'])/60_000)
    return None


def notify(text):
    token, chat = os.getenv('TELEGRAM_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat:
        raise RuntimeError('Telegram non configuré')
    req = Request('https://api.telegram.org/bot'+token+'/sendMessage',
                  data=urlencode(dict(chat_id=chat, text=text, parse_mode='HTML',
                                      disable_web_page_preview='true')).encode())
    with urlopen(req, timeout=15) as response:
        if not json.load(response).get('ok'):
            raise RuntimeError('Telegram a refusé le message')


def message(sym, zone, oi, delta):
    oi_text = f"{oi['pct']:+.2f} % sur {oi['minutes']:.0f} min" if oi else 'historique insuffisant'
    confirmation = ('OI en hausse et pression acheteuse récente' if oi and oi['pct'] >= .5 and delta and delta['buy_pct'] >= 55 else 'structure repérée, confirmation OI/flux non acquise')
    flow_text = (f"{delta['buy_pct']:.0f} % achats agressifs · échantillon {delta['seconds']:.0f} s / "
                 f"{delta['count']} transactions") if delta else 'indisponible / couverture insuffisante'
    return (f"👀 <b>RADAR ALT — PRÉALERTE RÉSISTANCE M15</b>\n{escape(sym)} · Zoomex\n"
            f"Zone : <code>{zone['low']:.8g}</code> à <code>{zone['high']:.8g}</code>\n"
            f"{zone['tests']} tests distincts · compression : {'oui' if zone['compression'] else 'non'}"
            f" · creux remontants : {'oui' if zone['rising_lows'] else 'non'}\n"
            f"OI en unités de base : {oi_text}\nFlux récent : {flow_text}\n"
            f"Lecture : {confirmation}\n"
            "Configuration expérimentale à surveiller, aucun signal d’achat.\n"
            "Le flux récent ne constitue pas un CVD M15 complet.\n"
            f"https://www.tradingview.com/chart/?symbol=ZOOMEX%3A{sym}.P&interval=15")


def event(row):
    with open(EVENTS, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    import radar_alt as radar
    dry = '--dry-run' in __import__('sys').argv
    # A malformed existing state must fail, not erase deduplication history.
    state = json.load(open(STATE)) if os.path.exists(STATE) else {'oi': {}, 'zones': {}}
    tick = api('tickers', category='linear')
    now = int(tick['time'])
    infos = radar.instruments()
    symbols = sorted([r for r in tick['result']['list'] if r['symbol'].endswith('USDT')
                      and float(r.get('turnover24h', 0)) >= radar.LIQ_MIN
                      and r['symbol'] != 'BTCUSDT' and radar.est_crypto(r['symbol'], infos)],
                     key=lambda r: float(r['turnover24h']), reverse=True)[:radar.PAIRES_MAX]
    if not symbols:
        raise RuntimeError('Univers Zoomex vide')
    ok = errors = alerts = 0
    for ticker in symbols:
        sym = ticker['symbol']
        try:
            res = api('kline', category='linear', symbol=sym, interval='15', limit=200)
            bars = candles(res['result']['list'], now)
            if len(bars) < 80:
                continue
            ok += 1
            oi = None
            try:
                value = float(ticker['openInterest'])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError('OI invalide')
                oi = oi_change(state['oi'].get(sym), value, now)
                state['oi'][sym] = dict(t=now, oi=value)
            except (KeyError, ValueError, TypeError):
                pass
            old = state['zones'].get(sym) if not dry else None
            if old:
                # Process only candles after notification, not earlier action.
                later = [b for b in bars if b['t'] >= old['notified']]
                if later and old['status'] == 'watch':
                    broken = next((b for b in later if b['c'] > old['high']), None)
                    failed = next((b for b in later if b['c'] < old['support']), None)
                    if broken and (not failed or broken['t'] < failed['t']):
                        old['status'] = 'broken'
                        old['broken_at'] = broken['t']
                        event(dict(event='breakout_close', sym=sym, now=now, bar=broken, zone=old))
                    elif failed:
                        old['status'] = 'invalid'
                        event(dict(event='invalid', sym=sym, now=now, bar=failed, zone=old))
                if old['status'] == 'broken' and any(b['t'] > old['broken_at'] and b['c'] < old['low'] for b in later):
                    old['status'] = 'reentered'
                    event(dict(event='reentry', sym=sym, now=now, zone=old))
            zone = detect(bars, now)
            if not zone:
                continue
            # Same resistance stays muted for 48h, even if estimated level drifts.
            if old and now-old['notified'] < 48*3_600_000 and abs(zone['level']-old['level']) < max(zone['atr'], old['atr']):
                continue
            # Never send an old closed-candle setup if the live price has already escaped.
            live = float(ticker['lastPrice'])
            if not zone['low']-.8*zone['atr'] <= live <= zone['high']:
                continue
            delta = None
            try:
                trades = api('recent-trade', category='linear', symbol=sym, limit=1000)
                delta = flow(trades['result']['list'], int(trades['time']))
            except Exception as exc:
                print(sym, 'flux indisponible', type(exc).__name__)
            # Structural warning remains useful when OI or flow is unavailable; show this explicitly.
            if dry:
                print(message(sym, zone, oi, delta))
                continue
            notify(message(sym, zone, oi, delta))
            state['zones'][sym] = dict(zone, notified=now, status='watch', oi=oi, flow=delta)
            event(dict(event='prealert', sym=sym, now=now, zone=zone, oi=oi, flow=delta))
            alerts += 1
        except Exception as exc:
            errors += 1
            print(sym, type(exc).__name__, str(exc)[:100])
    if not ok:
        raise RuntimeError('Aucune paire analysée : vérifier API Zoomex')
    if not dry:
        with open(STATE+'.tmp', 'w') as f:
            json.dump(state, f, ensure_ascii=False, allow_nan=False)
        os.replace(STATE+'.tmp', STATE)
    print(json.dumps(dict(analysed=ok, errors=errors, alerts=alerts, dry_run=dry)))


if __name__ == '__main__':
    main()
