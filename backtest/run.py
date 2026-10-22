"""Backtest : rejoue une crue réelle hors ligne avec la même decide() que l'agent live. Owner : S.

Entrée : CSV au format replay (station_code,ts,h_mm), plusieurs stations possibles.
Compare trois stratégies sur le moment où le 1er emplacement (A1) est touché :
  - naive    : alerte quand la hauteur à Vallon dépasse un seuil fixe (2 m)
  - agent_ref: l'agent avec la seule station du site (pente + ETA)
  - agent    : l'agent complet (station du site + station amont)
Compte aussi les fausses alertes avant le début de la crue.

python -m backtest.run   (crue oct. 2024 + été 2024 par défaut)
"""
import copy
import csv
import json
import sys
from datetime import datetime

from agent.decide import decide

REF, AMONT = "V505401001", "V501401001"
DELAI_AMONT_H = 5
SEUILS = {REF: {"pente_alerte_mm_h": 150, "h_alerte_mm": 2500},
          AMONT: {"pente_alerte_mm_h": 150, "h_alerte_mm": 2000}}
EMPLACEMENTS = [(f"A{i}", 3000 + 200 * (i - 1)) for i in range(1, 9)]  # mêmes valeurs que seed_site.sql
SEUIL_NAIF_MM = 2000


def charger(path):
    series = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            t = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            series.setdefault(r["station_code"], []).append((t, float(r["h_mm"])))
    return {k: sorted(v) for k, v in series.items()}


def pente(serie, i, fenetre_h):
    t1, h1 = serie[i]
    pts = [p for p in serie[: i + 1] if (t1 - p[0]).total_seconds() <= fenetre_h * 3600]
    if len(pts) < 2:
        return 0.0
    dt = (t1 - pts[0][0]).total_seconds() / 3600
    return (h1 - pts[0][1]) / dt if dt > 0.2 else 0.0


def premieres_alertes(serie, seuil, amont):
    """Liste des instants où decide() passe en ALERTE/CRITIQUE (front montant)."""
    out, actif = [], False
    for i, (t, h) in enumerate(serie):
        p = max(pente(serie, i, 1), pente(serie, i, 3))
        d = decide(h, p, DELAI_AMONT_H if amont else 0, seuil, EMPLACEMENTS, amont=amont)
        on = d.niveau in ("ALERTE", "CRITIQUE")
        if on and not actif:
            out.append(t)
        actif = on
    return out


def avance(crue, seuils, t_a1):
    al = premieres_alertes(crue[REF], seuils[REF], amont=False) + premieres_alertes(crue[AMONT], seuils[AMONT], amont=True)
    t = min(al) if al else None
    return t, (round((t_a1 - t).total_seconds() / 3600, 1) if t else None)


def fausses(calme, seuils):
    return {c: premieres_alertes(calme[c], seuils[c], amont=(c == AMONT)) for c in (REF, AMONT)}


def apprendre(calme, seuils, alertes):
    """Simule le gérant qui répond « fausse alerte » : même règle que memory.appliquer_verdict."""
    nouv = copy.deepcopy(seuils)
    for c, ts in alertes.items():
        serie = calme[c]
        for t in ts:
            i = [x[0] for x in serie].index(t)
            p = max(pente(serie, i, 1), pente(serie, i, 3))
            nouv[c]["pente_alerte_mm_h"] = max(nouv[c]["pente_alerte_mm_h"], round(p * 1.2))
            nouv[c]["version"] = nouv[c].get("version", 1) + 1
    return nouv


def main(path_crue, path_calme):
    crue, calme = charger(path_crue), charger(path_calme)
    ref = crue[REF]
    t_a1 = next(t for t, h in ref if h >= EMPLACEMENTS[0][1])
    t_pic = max(ref, key=lambda x: x[1])[0]
    jours_calme = round((max(t for v in calme.values() for t, _ in v) - min(t for v in calme.values() for t, _ in v)).days)

    t_naif = next(t for t, h in ref if h > SEUIL_NAIF_MM)
    t_ref, av_ref = avance({REF: ref, AMONT: []}, SEUILS, t_a1)
    t_v1, av_v1 = avance(crue, SEUILS, t_a1)
    fa_v1 = fausses(calme, SEUILS)
    seuils_v2 = apprendre(calme, SEUILS, fa_v1)
    t_v2, av_v2 = avance(crue, seuils_v2, t_a1)
    fa_v2 = fausses(calme, seuils_v2)
    v = calme[REF]
    fa_naif = [t for i, (t, h) in enumerate(v) if h > SEUIL_NAIF_MM and (i == 0 or v[i - 1][1] <= SEUIL_NAIF_MM)]
    n = lambda d: sum(len(x) for x in d.values())

    out = {
        "donnees": {"crue": path_crue, "periode_calme": path_calme, "jours_calmes": jours_calme,
                    "A1_touche": t_a1.isoformat(), "pic": {"ts": t_pic.isoformat(), "h_mm": max(h for _, h in ref)}},
        "resultats": {
            "naive_seuil_fixe_2m": {"premiere_alerte": t_naif.isoformat(), "avance_sur_A1_h": round((t_a1 - t_naif).total_seconds() / 3600, 1),
                                    "fausses_alertes": len(fa_naif)},
            "agent_station_site_seule": {"premiere_alerte": t_ref.isoformat() if t_ref else None, "avance_sur_A1_h": av_ref},
            "agent_v1": {"premiere_alerte": t_v1.isoformat() if t_v1 else None, "avance_sur_A1_h": av_v1,
                         "fausses_alertes": n(fa_v1), "detail": {c: [t.isoformat() for t in ts] for c, ts in fa_v1.items()}},
            "agent_v2_apres_verdict": {"seuils": seuils_v2, "premiere_alerte": t_v2.isoformat() if t_v2 else None,
                                       "avance_sur_A1_h": av_v2, "fausses_alertes": n(fa_v2)},
        },
        "note": "Données réelles Hub'Eau/HydroPortail (crue oct. 2024 + juil.-août 2024). Hauteurs d'emplacement hypothétiques.",
    }
    with open("backtest/results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/crue_ardeche_2024-10.csv",
         sys.argv[2] if len(sys.argv) > 2 else "data/calme_ardeche_2024-07-08.csv")
