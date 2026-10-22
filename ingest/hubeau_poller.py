"""Hub'Eau hydrométrie temps réel -> Kafka hydro.raw, toutes les 2 min. Owner : B.

API sans clé : https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr
Hauteurs (grandeur_hydro=H) en mm.
"""
import json
import time

import httpx
from confluent_kafka import Producer

from config import KAFKA_TOPIC, SITE_ID, kafka_conf, postgres

HUBEAU = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr"


def stations_du_site() -> list[str]:
    with postgres() as conn:
        rows = conn.execute(
            "SELECT station_code FROM site_stations WHERE site_id = %s", (SITE_ID,)
        ).fetchall()
    return [r[0] for r in rows]


def fetch(stations: list[str], depuis_min: int = 10) -> list[dict]:
    params = {
        "code_entite": ",".join(stations),
        "grandeur_hydro": "H",
        "timestep": 5,
        "size": 1000,
        "fields": "code_station,date_obs,resultat_obs",
        "date_debut_obs": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - depuis_min * 60)
        ),
    }
    r = httpx.get(HUBEAU, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def main():
    producer = Producer(kafka_conf())
    stations = stations_du_site()
    while True:
        for obs in fetch(stations):
            msg = {
                "station_code": obs["code_station"],
                "ts": obs["date_obs"],
                "h_mm": obs["resultat_obs"],
                "source": "hubeau",
            }
            producer.produce(KAFKA_TOPIC, key=msg["station_code"], value=json.dumps(msg))
        producer.flush()
        time.sleep(120)


if __name__ == "__main__":
    main()
