"""Hub'Eau hydrométrie temps réel -> Kafka hydro.raw, toutes les 2 min. Owner : B.

API sans clé : https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr
Hauteurs (grandeur_hydro=H) en mm.

    python -m ingest.hubeau_poller              # boucle infinie -> Kafka
    python -m ingest.hubeau_poller --once       # un seul passage
    python -m ingest.hubeau_poller --dry-run    # affiche, n'envoie rien
    python -m ingest.hubeau_poller --direct     # plan B : écrit dans ClickHouse sans Kafka

Stations : table site_stations (PostgreSQL) du SITE_ID ; à défaut, variable STATIONS=a,b.
Source : Hub'Eau, avec repli automatique sur HydroPortail si l'API ne répond pas
(HYDRO_SOURCE=auto par défaut ; hubeau ou hydroportail pour forcer).
À couper pendant un replay (sinon live et rejoué se mélangent).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from config import KAFKA_TOPIC, SITE_ID

HUBEAU = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr"
PERIODE_S = 120
RELECTURE_MIN = 30  # on relit 30 min à chaque passage : robuste aux retards de Hub'Eau


def stations_du_site() -> list[str]:
    try:
        from config import postgres

        with postgres() as conn:
            rows = conn.execute(
                "SELECT station_code FROM site_stations WHERE site_id = %s", (SITE_ID,)
            ).fetchall()
        if rows:
            return [r[0] for r in rows]
    except Exception as e:  # Postgres pas encore seedé : on se rabat sur .env
        print(f"[poller] site_stations indisponible ({type(e).__name__}), repli sur STATIONS", file=sys.stderr)
    codes = [c.strip() for c in os.getenv("STATIONS", "").split(",") if c.strip()]
    if not codes:
        sys.exit("Aucune station : seeder db/seed_site.sql ou définir STATIONS dans .env")
    return codes


def fetch(stations: list[str], depuis: datetime) -> list[dict]:
    """Toutes les hauteurs depuis `depuis`, en suivant la pagination."""
    params = {
        "code_entite": ",".join(stations),
        "grandeur_hydro": "H",
        "size": 5000,
        "sort": "asc",
        "fields": "code_station,date_obs,resultat_obs",
        "date_debut_obs": depuis.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out, url = [], HUBEAU
    with httpx.Client(timeout=30) as client:
        while url:
            r = client.get(url, params=params)
            if r.status_code not in (200, 206):
                raise RuntimeError(f"Hub'Eau HTTP {r.status_code}: {r.text[:200]}")
            body = r.json()
            out += body.get("data", [])
            url, params = body.get("next"), None
    return out


def fetch_auto(stations: list[str], depuis: datetime, source: str = "auto") -> tuple[list[dict], str]:
    """Hub'Eau d'abord ; si l'API est injoignable (réseau du lieu, panne), repli sur HydroPortail.
    HYDRO_SOURCE=hubeau | hydroportail | auto (défaut)."""
    if source in ("auto", "hubeau"):
        try:
            return fetch(stations, depuis), "hubeau"
        except Exception as e:
            if source == "hubeau":
                raise
            print(f"[poller] Hub'Eau KO ({type(e).__name__}), repli HydroPortail", file=sys.stderr)
    from ingest import hydroportail

    obs = hydroportail.fetch_all(stations, depuis, datetime.now(timezone.utc))
    return [o for o in obs if o["date_obs"] >= depuis.strftime("%Y-%m-%dT%H:%M:%SZ")], "hydroportail"


def to_message(obs: dict) -> dict | None:
    """Observation Hub'Eau -> message du contrat hydro.raw. None si inexploitable."""
    if obs.get("resultat_obs") is None or not obs.get("date_obs"):
        return None
    ts = datetime.fromisoformat(obs["date_obs"].replace("Z", "+00:00"))
    return {
        "station_code": obs["code_station"],
        "ts": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "h_mm": float(obs["resultat_obs"]),
        "source": "hubeau",
    }


def nouveaux(obs: list[dict], dernier_ts: dict) -> list[dict]:
    """Ne garde que les mesures plus récentes que la dernière envoyée par station."""
    msgs = [m for m in map(to_message, obs) if m and m["ts"] > dernier_ts.get(m["station_code"], "")]
    for m in msgs:
        dernier_ts[m["station_code"]] = max(dernier_ts.get(m["station_code"], ""), m["ts"])
    return msgs


def envoyeur(mode: str):
    if mode == "kafka":
        from confluent_kafka import Producer

        from config import kafka_conf

        producer = Producer(kafka_conf())

        def send(msgs):
            for m in msgs:
                producer.produce(KAFKA_TOPIC, key=m["station_code"], value=json.dumps(m))
                producer.poll(0)
            producer.flush(20)

        return send
    if mode == "direct":
        from config import clickhouse

        ch = clickhouse()
        return lambda msgs: ch.insert(
            "hydro_obs",
            [[m["station_code"], datetime.strptime(m["ts"], "%Y-%m-%dT%H:%M:%SZ"), m["h_mm"], m["source"]]
             for m in msgs],
            column_names=["station_code", "ts", "h_mm", "source"],
        )
    return lambda msgs: [print(m) for m in msgs[-10:]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--direct", action="store_true", help="plan B : ClickHouse sans Kafka")
    a = ap.parse_args()
    mode = "dry" if a.dry_run else "direct" if a.direct else "kafka"

    stations, dernier_ts = stations_du_site(), {}
    send = envoyeur(mode)
    source = os.getenv("HYDRO_SOURCE", "auto")
    print(f"[poller] {len(stations)} stations {stations}, mode={mode}, source={source}, toutes les {PERIODE_S}s")
    while True:
        t0 = time.time()
        try:
            depuis = datetime.now(timezone.utc) - timedelta(minutes=RELECTURE_MIN)
            obs, via = fetch_auto(stations, depuis, source)
            msgs = nouveaux(obs, dernier_ts)
            if msgs:
                send(msgs)
            print(f"[poller] {datetime.now():%H:%M:%S} {len(msgs)} nouvelles mesures (via {via})")
        except Exception as e:  # la boucle ne meurt jamais pour une erreur réseau
            print(f"[poller] ERREUR {type(e).__name__}: {e}", file=sys.stderr)
        if a.once:
            break
        time.sleep(max(0, PERIODE_S - (time.time() - t0)))


if __name__ == "__main__":
    main()
