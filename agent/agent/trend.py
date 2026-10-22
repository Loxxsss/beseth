"""Tendance par station : hauteur actuelle + pente (mm/h) sur 1 h et 3 h. Owner : S.

La fenêtre est mesurée en TEMPS DE LA DONNÉE (max(ts) de la station), pas en now() :
en live max(ts) ≈ now ; en replay accéléré les ts décalés peuvent être dans le futur,
et les mm/h restent justes tant que replay.py conserve l'écart entre les points.
"""
from dataclasses import dataclass

from config import clickhouse

SQL = """
WITH (SELECT max(ts) FROM hydro_obs WHERE station_code = {code:String}) AS t_max
SELECT argMax(h_mm, ts) AS h_now,
       simpleLinearRegression(toUnixTimestamp(ts), h_mm).1 * 3600 AS pente_mm_h,
       argMax(source, ts) AS source,
       count() AS n
FROM hydro_obs
WHERE station_code = {code:String}
  AND ts > t_max - INTERVAL {heures:UInt8} HOUR
"""


@dataclass
class Tendance:
    station_code: str
    h_now: float
    pente_mm_h: float  # la plus forte des pentes 1 h / 3 h
    source: str


def tendance(ch, code: str) -> Tendance | None:
    pentes, dernier = [], None
    for heures in (1, 3):
        rows = ch.query(SQL, parameters={"code": code, "heures": heures}).result_rows
        if not rows or rows[0][3] == 0:
            continue
        h_now, p, source, n = rows[0]
        dernier = (h_now, source)
        if n >= 2 and p == p:  # au moins 2 points, pas NaN
            pentes.append(p)
    if dernier is None:
        return None
    return Tendance(code, float(dernier[0]), max(pentes, default=0.0), dernier[1])


def tendances(stations: list[str]) -> dict[str, Tendance]:
    ch = clickhouse()
    out = {}
    for code in stations:
        t = tendance(ch, code)
        if t:
            out[code] = t
    return out
