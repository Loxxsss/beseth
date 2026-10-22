"""Tendance par station : hauteur actuelle + pente (mm/h) sur 1 h et 3 h. Owner : S.

Lit les vues ClickHouse de B (default.pente_1h / default.pente_3h), calées sur le
dernier point de chaque station (temps de la donnée, pas now()) : marche en live
comme en replay accéléré.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import clickhouse


@dataclass
class Tendance:
    station_code: str
    h_now: float
    pente_mm_h: float  # la plus forte des pentes 1 h / 3 h
    source: str


def tendances(stations: list[str]) -> dict[str, Tendance]:
    ch = clickhouse()
    params = {"stations": stations}
    vues = {}
    for vue in ("pente_1h", "pente_3h"):
        rows = ch.query(
            f"SELECT station_code, h_now, pente_mm_h FROM {vue} WHERE station_code IN {{stations:Array(String)}}",
            parameters=params,
        ).result_rows
        vues[vue] = {r[0]: r for r in rows}
    sources = dict(ch.query(
        "SELECT station_code, argMax(source, ts) FROM hydro_obs "
        "WHERE station_code IN {stations:Array(String)} GROUP BY station_code",
        parameters=params,
    ).result_rows)

    out = {}
    for code in stations:
        r1, r3 = vues["pente_1h"].get(code), vues["pente_3h"].get(code)
        r = r1 or r3
        if not r:
            continue
        pentes = [x[2] for x in (r1, r3) if x and x[2] is not None and x[2] == x[2]]  # filtre NaN
        out[code] = Tendance(code, float(r[1]), max(pentes, default=0.0), sources.get(code, "hubeau"))
    return out
