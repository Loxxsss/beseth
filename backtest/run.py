"""Backtest : rejoue une crue réelle hors ligne avec la même decide() que l'agent live. Owner : S.

Entrée : CSV au format replay (station_code,ts,h_mm), plusieurs stations possibles.
Compare trois stratégies sur le moment où le 1er emplacement (A1) est touché :
  - naive    : alerte quand la hauteur à Vallon dépasse un seuil fixe (2 m)
  - agent_ref: l'agent avec la seule station du site (pente + ETA)
  - agent    : l'agent complet (station du site + station amont)
Compte aussi les fausses alertes avant le début de la crue.

python -m backtest.run data/crue_ardeche_2024-10.csv
"""
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


def main(path):
    s = charger(path)
    ref = s[REF]
    t_a1 = next(t for t, h in ref if h >= EMPLACEMENTS[0][1])
    t_pic = max(ref, key=lambda x: x[1])[0]
    # début de crue = premier dépassement d'1 m à la station de référence
    t_debut = next(t for t, h in ref if h >= 1000)

    alertes = {
        "naive": [next(t for t, h in ref if h > SEUIL_NAIF_MM)],
        "agent_ref": premieres_alertes(ref, SEUILS[REF], amont=False),
    }
    alertes["agent"] = sorted(alertes["agent_ref"] + (premieres_alertes(s[AMONT], SEUILS[AMONT], amont=True) if AMONT in s else []))

    h = lambda a, b: round((b - a).total_seconds() / 3600, 1)
    res = {}
    for nom, ts in alertes.items():
        vraies = [t for t in ts if t >= min(t_debut, t_a1).replace(hour=0, minute=0)]
        premiere = min(ts) if ts else None
        res[nom] = {
            "premiere_alerte": premiere.isoformat() if premiere else None,
            "avance_sur_A1_h": h(premiere, t_a1) if premiere else None,
            "avance_sur_pic_h": h(premiere, t_pic) if premiere else None,
            "fausses_alertes_avant_crue": len([t for t in ts if t < t_debut.replace(hour=0, minute=0)]),
        }
    out = {
        "crue": path,
        "A1_touche": t_a1.isoformat(),
        "pic": {"ts": t_pic.isoformat(), "h_mm": max(h_ for _, h_ in ref)},
        "resultats": res,
        "note": "1 crue réelle (Hub'Eau, oct. 2024) ; hauteurs d'emplacement hypothétiques ; à compléter par des périodes calmes pour un vrai taux de fausses alertes",
    }
    with open("backtest/results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/crue_ardeche_2024-10.csv")
