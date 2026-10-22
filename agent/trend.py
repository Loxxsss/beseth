"""Tendance par station : hauteur actuelle + pente (mm/h) sur 1 h et 3 h. Owner : S.

Lit les vues ClickHouse de B (default.pente_1h / default.pente_3h), calées sur le
dernier point de chaque station (temps de la donnée, pas now()) : marche en live
comme en replay accéléré.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from config import clickhouse


@dataclass
class Tendance:
    station_code: str
    h_now: float
    pente_mm_h: float          # la plus forte des pentes 1 h / 3 h (utilisée par decide)
    source: str
    pente_1h: float | None = None
    pente_3h: float | None = None
    derniere_mesure: datetime | None = None

    def age_min(self) -> float | None:
        if not self.derniere_mesure:
            return None
        t = self.derniere_mesure if self.derniere_mesure.tzinfo else self.derniere_mesure.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60


def _propre(x):
    return None if x is None or x != x else float(x)  # None / NaN -> None


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
    meta = {r[0]: (r[1], r[2]) for r in ch.query(
        "SELECT station_code, argMax(source, ts), max(ts) FROM hydro_obs "
        "WHERE station_code IN {stations:Array(String)} GROUP BY station_code",
        parameters=params,
    ).result_rows}

    out = {}
    for code in stations:
        r1, r3 = vues["pente_1h"].get(code), vues["pente_3h"].get(code)
        r = r1 or r3
        if not r:
            continue
        p1 = _propre(r1[2]) if r1 else None
        p3 = _propre(r3[2]) if r3 else None
        source, t_max = meta.get(code, ("hubeau", None))
        out[code] = Tendance(code, float(r[1]), max([p for p in (p1, p3) if p is not None], default=0.0),
                             source, p1, p3, t_max)
    return out
