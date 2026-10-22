"""Tendance par station : hauteur actuelle + pente (mm/h) sur 1 h et 3 h. Owner : S."""
from dataclasses import dataclass

from config import clickhouse

SQL = """
SELECT station_code,
       argMax(h_mm, ts) AS h_now,
       simpleLinearRegression(toUnixTimestamp(ts), h_mm).1 * 3600 AS pente_mm_h,
       argMax(source, ts) AS source
FROM hydro_obs
WHERE station_code IN {stations:Array(String)}
  AND ts > now() - INTERVAL {heures:UInt8} HOUR
GROUP BY station_code
"""


@dataclass
class Tendance:
    station_code: str
    h_now: float
    pente_mm_h: float  # la plus forte des pentes 1 h / 3 h
    source: str


def tendances(stations: list[str]) -> dict[str, Tendance]:
    ch = clickhouse()
    par_fenetre = {}
    for heures in (1, 3):
        res = ch.query(SQL, parameters={"stations": stations, "heures": heures})
        par_fenetre[heures] = {r[0]: r for r in res.result_rows}

    out = {}
    for code in stations:
        r1, r3 = par_fenetre[1].get(code), par_fenetre[3].get(code)
        r = r1 or r3
        if not r:
            continue
        pentes = [x[2] for x in (r1, r3) if x and x[2] == x[2]]  # filtre NaN
        out[code] = Tendance(code, float(r[1]), max(pentes, default=0.0), r[3])
    return out
