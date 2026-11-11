import numpy as np
import pandas as pd

import radar_alt as R


def serie(prix, t0=0, pas=R.H4):
    prix = np.asarray(prix, dtype=float)
    return pd.DataFrame(dict(t=t0 + pas * np.arange(len(prix)), o=prix, h=prix * 1.01, l=prix * 0.99,
                             c=prix, v=1.0))


def univers(n=30, monte=("AAAUSDT",), casse=()):
    M = {}
    for i in range(n):
        M[f"S{i}USDT"] = dict(prix=1.0, atr=0.02, r7=i / 1000, r30=i / 1000, h4_haussier=True,
                              jour_haussier=True, bas60=0.5)
    for s in monte:
        M[s] = dict(prix=2.0, atr=0.05, r7=0.5, r30=0.9, h4_haussier=True, jour_haussier=True, bas60=1.0)
    for s in casse:
        M[s] = dict(prix=0.9, atr=0.03, r7=-0.3, r30=-0.5, h4_haussier=False, jour_haussier=False, bas60=1.0)
    return M


def test_mesures_historique_trop_court():
    assert R.mesures(serie(np.linspace(1, 2, 50)), None) is None


def test_mesures_plus_bas_60j_sans_la_bougie_en_cours():
    prix = np.r_[np.full(400, 10.0), 5.0]
    m = R.mesures(serie(prix), serie(np.linspace(1, 2, 80), pas=R.JOUR))
    assert m["bas60"] == 10.0 * 0.99 and m["prix"] < m["bas60"]
    assert m["jour_haussier"] and m["t"] == 400 * R.H4 + R.H4


def test_detecter_leader_et_cassure():
    c = R.detecter(univers(casse=("ZZZUSDT",)))
    assert ("AAAUSDT", "leader") in c and ("ZZZUSDT", "cassure_bas") in c
    assert ("S0USDT", "leader") not in c and ("ZZZUSDT", "leader") not in c


def test_leader_exige_la_tendance():
    M = univers()
    M["AAAUSDT"]["jour_haussier"] = False
    assert ("AAAUSDT", "leader") not in R.detecter(M)


def test_pas_de_classement_si_univers_trop_petit():
    assert R.detecter(univers(n=5)) == {}


def test_signal_seulement_si_etat_nouveau():
    vus, cand = {}, {("AAAUSDT", "leader"): {}}
    assert R.nouveaux_signaux(cand, vus, 100 * R.H4) == [("AAAUSDT", "leader")]
    assert R.nouveaux_signaux(cand, vus, 101 * R.H4) == []                 # état déjà connu
    assert R.nouveaux_signaux(cand, vus, (101 + R.REPOS_H4) * R.H4) == []  # pas assez de repos
    assert R.nouveaux_signaux(cand, vus, (102 + 2 * R.REPOS_H4) * R.H4) == [("AAAUSDT", "leader")]


def test_retenir_limite_par_sens_et_prefere_la_liquidite():
    neufs = [(f"S{i}USDT", "leader") for i in range(5)] + [("ZUSDT", "cassure_bas")]
    g = R.retenir(neufs, {f"S{i}USDT": i for i in range(5)})
    assert [x for x in g if x[1] == "leader"] == [("S4USDT", "leader"), ("S3USDT", "leader")]
    assert ("ZUSDT", "cassure_bas") in g


def test_ticket_long_et_short():
    assert R.ticket(100, 5, "leader") == (100, 90, 130)
    assert R.ticket(100, 5, "cassure_bas") == (100, 110, 70)


def test_suivre_short():
    s = dict(sens=-1, t_decl=0, entree=100, sl=110, objectif=70, objectif_r=3.0, max_h=168)
    h1 = pd.DataFrame(dict(t=[0, R.H1], h=[105.0, 101.0], l=[95.0, 69.0], c=[96.0, 70.0]))
    assert R.suivre(s, h1)[:2] == ("OBJECTIF", 3.0)
    h1.loc[0, "h"] = 111.0
    assert R.suivre(s, h1)[:2] == ("SL", -1.0)


def test_migration_v1_garde_les_declenchements(tmp_path, monkeypatch):
    import json
    p = tmp_path / "etat.json"
    p.write_text(json.dumps(dict(dernier_resume=7, setups={
        "A": dict(sym="AUSDT", type="retournement", etape="declenche", t_decl=5, entree=1, sl=0.9, objectif=1.2),
        "B": dict(sym="BUSDT", type="continuation", etape="formation", t_decl=0)})))
    monkeypatch.setattr(R, "ETAT", str(p))
    e = R.charger_etat()
    assert e["version"] == 2 and list(e["suivis"]) == ["A"] and "vus" not in e
    assert e["suivis"]["A"]["max_h"] == 72 and e["dernier_resume"] == 7


def test_boutons_ordre_portent_le_ticket():
    s = dict(sym="DOTUSDT", sens=-1, entree=0.8316, sl=0.8752, objectif=0.7008)
    b = R.boutons_ordre(s, 0.0001)["inline_keyboard"][0]
    assert b[0]["callback_data"] == "p|DOTUSDT|S|0.8316|0.8752|0.7008" and "SHORT DOT" in b[0]["text"]
    assert b[1]["callback_data"] == "i"
    assert R.boutons_ordre(dict(s, sym="X" * 60 + "USDT"), 0.0001) is None       # trop long pour Telegram


def test_pas_de_short_si_objectif_impossible():
    M = univers(casse=("ZZZUSDT",))
    M["ZZZUSDT"]["atr"] = 0.2                      # 2 ATR x 3 R = 1,2 : plus que le prix (0,9)
    assert ("ZZZUSDT", "cassure_bas") not in R.detecter(M)
