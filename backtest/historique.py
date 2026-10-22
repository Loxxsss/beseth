"""Backtest sur 7 ans de données réelles (Hub'Eau / HydroPortail, hauteurs interpolées horaires,
Vallon-Pont-d'Arc + Vogüé, 2019-2025). Owner : S.

python -m backtest.historique        -> backtest/results_historique.json + tableau à l'écran

Définitions (identiques pour toutes les stratégies) :
- crue           = épisode où Vallon atteint la hauteur d'inondation de A1 (3 m) ; épisodes séparés de > 48 h
- détectée       = au moins une alerte dans les 24 h qui précèdent l'arrivée de l'eau sur A1
- anticipation   = arrivée sur A1 - première alerte de cette fenêtre de 24 h
- fausse alerte  = déclenchement (front montant ALERTE/CRITIQUE) qui n'est suivi d'aucune arrivée sur A1
                   dans les 24 h, hors épisodes de crue (± 48 h)
Stratégies :
- naive        : alerte si Vallon > 2 m (seuil fixe, ce que ferait un gérant avec un niveau de référence)
- agent_v1     : decide() avec les seuils de départ (pente + ETA + station amont), sans apprentissage
- agent_appris : même agent, mais chaque fausse alerte relève le seuil de pente de la station (× 1,2 de
                 la pente déclenchante), appliqué dans l'ordre chronologique, comme le ferait le gérant
"""
from __future__ import annotations

import bisect
import csv
import json
from datetime import datetime, timedelta
from statistics import median

from agent.decide import decide

REF, AMONT = "V505401001", "V501401001"
DELAI_AMONT_H = 5
SEUILS_V1 = {REF: {"pente_alerte_mm_h": 150, "h_alerte_mm": 2500},
             AMONT: {"pente_alerte_mm_h": 150, "h_alerte_mm": 2000}}
EMPLACEMENTS = [(f"A{i}", 3000 + 200 * (i - 1)) for i in range(1, 9)]
H_A1 = EMPLACEMENTS[0][1]
SEUIL_NAIF_MM = 2000
FENETRE = timedelta(hours=24)
SEP_EPISODES = timedelta(hours=48)


def charger(path):
    s = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            t = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            s.setdefault(r["station_code"], []).append((t, float(r["h_mm"])))
    return {k: sorted(v) for k, v in s.items()}


def pentes(serie):
    """max(pente 1 h, pente 3 h) en chaque point (différence premier/dernier point de la fenêtre)."""
    ts = [t.timestamp() for t, _ in serie]
    out = []
    for i, (t, h) in enumerate(serie):
        best = 0.0
        for fen in (1, 3):
            j = bisect.bisect_left(ts, ts[i] - fen * 3600)
            dt = (ts[i] - ts[j]) / 3600
            if j < i and dt > 0.2:
                best = max(best, (h - serie[j][1]) / dt)
        out.append(best)
    return out


def episodes_crue(ref):
    eps, dernier = [], None
    for t, h in ref:
        if h >= H_A1:
            if dernier is None or t - dernier > SEP_EPISODES:
                eps.append({"a1": t, "fin": t, "pic": h})
            e = eps[-1]
            e["fin"], e["pic"] = t, max(e["pic"], h)
            dernier = t
    return eps


def fronts(serie, p, seuils_init, amont, apprendre, arrivees):
    """Déclenchements (front montant) avec apprentissage optionnel, dans l'ordre chronologique."""
    seuil = dict(seuils_init)
    out, actif = [], False
    a1_ts = [a.timestamp() for a in arrivees]
    for i, (t, h) in enumerate(serie):
        d = decide(h, p[i], DELAI_AMONT_H if amont else 0, seuil, EMPLACEMENTS, amont=amont)
        on = d.niveau in ("ALERTE", "CRITIQUE")
        if on and not actif:
            k = bisect.bisect_left(a1_ts, t.timestamp())
            vraie = k < len(a1_ts) and a1_ts[k] - t.timestamp() <= FENETRE.total_seconds()
            out.append((t, vraie, p[i]))
            if apprendre and not vraie:
                seuil["pente_alerte_mm_h"] = max(seuil["pente_alerte_mm_h"], p[i] * 1.2)
        actif = on
    return out, seuil


def dans_crue(t, eps):
    return any(e["a1"] - SEP_EPISODES <= t <= e["fin"] + SEP_EPISODES for e in eps)


def evaluer(nom, declenchements, eps):
    res_crues = []
    for e in eps:
        dans = [t for t, _, _ in declenchements if e["a1"] - FENETRE <= t <= e["a1"]]
        res_crues.append({"a1": e["a1"].isoformat(), "pic_mm": e["pic"],
                          "detectee": bool(dans),
                          "anticipation_h": round((e["a1"] - min(dans)).total_seconds() / 3600, 1) if dans else None})
    fausses = [t for t, vraie, _ in declenchements if not vraie and not dans_crue(t, eps)]
    anticip = [c["anticipation_h"] for c in res_crues if c["detectee"]]
    return {
        "crues_detectees": f"{sum(c['detectee'] for c in res_crues)}/{len(res_crues)}",
        "anticipation_mediane_h": round(median(anticip), 1) if anticip else None,
        "anticipation_min_max_h": [min(anticip), max(anticip)] if anticip else None,
        "fausses_alertes": len(fausses),
        "fausses_alertes_par_an": None,
        "detail_crues": res_crues,
        "dates_fausses_alertes": [t.isoformat() for t in fausses],
    }


def main(path="data/historique_ardeche_2019-2025_horaire.csv"):
    s = charger(path)
    ref, amont = s[REF], s[AMONT]
    eps = episodes_crue(ref)
    arrivees = [e["a1"] for e in eps]
    annees = (ref[-1][0] - ref[0][0]).days / 365.25

    naive = []
    actif = False
    a1_ts = [a.timestamp() for a in arrivees]
    for t, h in ref:
        on = h > SEUIL_NAIF_MM
        if on and not actif:
            k = bisect.bisect_left(a1_ts, t.timestamp())
            naive.append((t, k < len(a1_ts) and a1_ts[k] - t.timestamp() <= FENETRE.total_seconds(), 0))
        actif = on

    p_ref, p_am = pentes(ref), pentes(amont)
    res = {"naive": evaluer("naive", naive, eps)}
    seuils_finaux = {}
    for nom, apprendre in (("agent_v1", False), ("agent_appris", True)):
        f_ref, s_ref = fronts(ref, p_ref, SEUILS_V1[REF], False, apprendre, arrivees)
        f_am, s_am = fronts(amont, p_am, SEUILS_V1[AMONT], True, apprendre, arrivees)
        res[nom] = evaluer(nom, sorted(f_ref + f_am), eps)
        if apprendre:
            seuils_finaux = {REF: round(s_ref["pente_alerte_mm_h"]), AMONT: round(s_am["pente_alerte_mm_h"])}
    for r in res.values():
        r["fausses_alertes_par_an"] = round(r["fausses_alertes"] / annees, 1)

    out = {
        "donnees": {"source": "Hub'Eau / HydroPortail, hauteurs interpolées horaires (HIn, pas 60 min)",
                    "stations": {REF: "L'Ardèche à Vallon-Pont-d'Arc", AMONT: "L'Ardèche à Vogüé (amont)"},
                    "periode": f"{ref[0][0]:%Y-%m-%d} -> {ref[-1][0]:%Y-%m-%d}", "annees": round(annees, 1),
                    "nb_crues_A1": len(eps), "hauteur_A1_mm": H_A1,
                    "note": "Rejeu de données historiques, pas des alertes en conditions réelles. "
                            "Hauteur d'inondation des emplacements = hypothèse du site de démo."},
        "resultats": res,
        "seuils_pente_apres_apprentissage_mm_h": seuils_finaux,
    }
    with open("backtest/results_historique.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"{out['donnees']['periode']} ({out['donnees']['annees']} ans), {len(eps)} crues atteignant A1 (3 m à Vallon)\n")
    print(f"{'':28}{'Seuil fixe 2 m':>16}{'Agent v1':>12}{'Agent appris':>14}")
    lig = lambda lab, k: print(f"{lab:28}" + "".join(f"{str(res[n][k]):>{w}}" for n, w in (("naive", 16), ("agent_v1", 12), ("agent_appris", 14))))
    lig("Crues détectées", "crues_detectees")
    lig("Anticipation médiane (h)", "anticipation_mediane_h")
    lig("Anticipation min-max (h)", "anticipation_min_max_h")
    lig("Fausses alertes (7 ans)", "fausses_alertes")
    lig("Fausses alertes / an", "fausses_alertes_par_an")
    print("\nSeuils de pente appris :", seuils_finaux)
    for c_n, c_a in zip(res["naive"]["detail_crues"], res["agent_appris"]["detail_crues"]):
        print(f"  crue {c_n['a1'][:16]}  pic {c_n['pic_mm']/1000:.1f} m   naïf {c_n['anticipation_h']} h   agent appris {c_a['anticipation_h']} h")


if __name__ == "__main__":
    main()
