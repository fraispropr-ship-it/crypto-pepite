"""Offline descriptive baseline from V1 radar_journal.csv.

NOT a V2 backtest: historical M15 candles and rejected candidates are not in
the journal. No claim about V2 profitability is possible from this report.
"""
import argparse
import csv
import json
from collections import defaultdict


def stats(rows, fee_rate=0.0006):
    if not rows:
        return dict(n=0, mean_gross_R=None, mean_net_R=None, total_gross_R=0,
                    total_net_R=0, sl=0, targets=0, expired=0)
    gross = net = 0.0
    for r in rows:
        entry, stop = float(r["entree"]), float(r["sl"])
        if entry <= stop or stop <= 0:
            raise ValueError("Invalid LONG entry/stop in journal")
        risk = entry - stop
        gross_r = float(r["resultat_R"])
        # Approximates exit from logged R for expiry, and fixed stop/target elsewhere.
        exit_price = entry + gross_r * risk
        fee_r = fee_rate * (entry + max(exit_price, 0)) / risk
        gross += gross_r
        net += gross_r - fee_r
    n = len(rows)
    return dict(n=n, mean_gross_R=round(gross/n, 4),
                mean_net_R=round(net/n, 4), total_gross_R=round(gross, 3),
                total_net_R=round(net, 3),
                sl=sum(r["statut"] == "SL" for r in rows),
                targets=sum(r["statut"] == "OBJECTIF" for r in rows),
                expired=sum(r["statut"].startswith("EXPIRE") for r in rows))


def report(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Forced expiry without prices is NOT a zero-return observation.
    rows = [r for r in rows if r["statut"] != "EXPIRE_SANS_DONNEES"]
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)
    return dict(disclaimer="Descriptive V1 baseline, not V2 backtest; costs estimated, slippage excluded.",
                overall=stats(rows), by_type={k: stats(v) for k,v in sorted(by_type.items())})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--journal", default="radar_journal.csv")
    a = p.parse_args()
    print(json.dumps(report(a.journal), indent=2, ensure_ascii=False))
