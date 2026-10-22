"""Rejoue une crue passée dans Kafka, accélérée (x60 par défaut). Owner : B.

CSV attendu : station_code,ts,h_mm   (ts ISO, trié par date)
Les messages portent source="replay" : le front affiche le badge REPLAY.
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone

from confluent_kafka import Producer

from config import KAFKA_TOPIC, kafka_conf


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--speed", type=float, default=60.0)
    args = p.parse_args()

    producer = Producer(kafka_conf())
    with open(args.csv) as f:
        rows = list(csv.DictReader(f))

    prev = None
    for row in rows:
        ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        if prev:
            time.sleep(max(0.0, (ts - prev).total_seconds() / args.speed))
        prev = ts
        msg = {
            "station_code": row["station_code"],
            # horodaté "maintenant" pour que l'agent le voie comme du flux frais
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "h_mm": float(row["h_mm"]),
            "source": "replay",
        }
        producer.produce(KAFKA_TOPIC, key=msg["station_code"], value=json.dumps(msg))
        producer.poll(0)
    producer.flush()


if __name__ == "__main__":
    main()
