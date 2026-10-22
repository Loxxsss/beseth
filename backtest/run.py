"""Backtest : rejoue des crues passées hors ligne avec la même decide(). Owner : S.

Entrée : un CSV par crue (station_code,ts,h_mm) + l'heure du pic connue.
Sortie : backtest/results.json avec, pour l'agent ET pour la baseline naïve
(alerte quand h > seuil fixe), l'avance en heures sur le pic et le nombre de fausses alertes.

python -m backtest.run data/crue1.csv data/crue2.csv ...
"""
import csv
import json
import sys
from datetime import datetime
from statistics import median

from agent.decide import decide

SEUIL = {"pente_alerte_mm_h": 80, "h_alerte_mm": 1800}   # mêmes valeurs que seed_site.sql
EMPLACEMENTS = [(f"A{i}", 2000 + 50 * (i - 1)) for i in range(1, 9)]
SEUIL_NAIF_MM = 2000                                      # baseline : alerte quand h > 2 m


def charger(path):
    with open(path) as f:
        rows = [(datetime.fromisoformat(r["ts"].replace("Z", "+00:00")), float(r["h_mm"])) for r in csv.DictReader(f)]
    return sorted(rows)


def pente(rows, i, fenetre_h=1.0):
    t1, h1 = rows[i]
    pts = [(t, h) for t, h in rows[: i + 1] if (t1 - t).total_seconds() <= fenetre_h * 3600]
    if len(pts) < 2:
        return 0.0
    (t0, h0) = pts[0]
    dt = (t1 - t0).total_seconds() / 3600
    return (h1 - h0) / dt if dt else 0.0


def evaluer(rows):
    t_pic = max(rows, key=lambda r: r[1])[0]
    premiere_agent = premiere_naif = None
    for i, (t, h) in enumerate(rows):
        d = decide(h, max(pente(rows, i, 1), pente(rows, i, 3)), 0, SEUIL, EMPLACEMENTS)
        if premiere_agent is None and d.niveau in ("ALERTE", "CRITIQUE"):
            premiere_agent = t
        if premiere_naif is None and h > SEUIL_NAIF_MM:
            premiere_naif = t
    avance = lambda t0: None if t0 is None else round((t_pic - t0).total_seconds() / 3600, 1)
    return {"avance_agent_h": avance(premiere_agent), "avance_naif_h": avance(premiere_naif)}


def main(paths):
    res = {p: evaluer(charger(p)) for p in paths}
    agent = [r["avance_agent_h"] for r in res.values() if r["avance_agent_h"] is not None]
    naif = [r["avance_naif_h"] for r in res.values() if r["avance_naif_h"] is not None]
    out = {
        "crues": res,
        "mediane_avance_agent_h": median(agent) if agent else None,
        "mediane_avance_naif_h": median(naif) if naif else None,
        # TODO S : rejouer aussi des périodes SANS crue pour compter les fausses alertes
    }
    with open("backtest/results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
