"""Charge ~30 jours d'historique Hub'Eau directement dans ClickHouse. Owner : B."""
import time
from datetime import datetime

import httpx

from config import clickhouse
from ingest.hubeau_poller import HUBEAU, stations_du_site


def main(jours: int = 30):
    ch = clickhouse()
    debut = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - jours * 86400))
    for station in stations_du_site():
        url, params = HUBEAU, {
            "code_entite": station,
            "grandeur_hydro": "H",
            "size": 20000,
            "fields": "code_station,date_obs,resultat_obs",
            "date_debut_obs": debut,
        }
        rows = []
        while url:
            r = httpx.get(url, params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            rows += [
                (o["code_station"], datetime.fromisoformat(o["date_obs"][:19]), o["resultat_obs"], "hubeau")
                for o in body.get("data", [])
            ]
            url, params = body.get("next"), None
        if rows:
            ch.insert("hydro_obs", rows, column_names=["station_code", "ts", "h_mm", "source"])
        print(station, len(rows), "observations")


if __name__ == "__main__":
    main()
