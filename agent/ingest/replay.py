"""Rejoue une crue passée dans Kafka, accélérée. Owner : B.

CSV : station_code,ts,h_mm (ts ISO UTC) — ex. data/crue_ardeche_2024-10.csv
Les timestamps sont DÉCALÉS d'un offset constant (offset = maintenant - début de fenêtre) :
l'écart entre points est conservé, donc les pentes en mm/h aussi. En accéléré, les ts
décalés passent dans le futur : l'agent mesure ses fenêtres sur max(ts), pas sur now().
Les messages portent source="replay" (badge REPLAY dans le front).
Couper le poller live pendant un replay.

Démo conseillée (~3 min) :
python -m ingest.replay --csv data/crue_ardeche_2024-10.csv \
    --debut 2024-10-16T08:00 --fin 2024-10-16T17:00 --speed 180
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone

from confluent_kafka import Producer

from config import KAFKA_TOPIC, kafka_conf


def parse(ts: str) -> datetime:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--speed", type=float, default=180.0)
    p.add_argument("--debut", help="début de fenêtre (ISO, UTC)")
    p.add_argument("--fin", help="fin de fenêtre (ISO, UTC)")
    p.add_argument("--prelude-h", type=float, default=3.0,
                   help="heures avant --debut injectées d'un coup (pour que les pentes 1 h / 3 h existent dès le départ)")
    args = p.parse_args()

    with open(args.csv) as f:
        rows = sorted(((parse(r["ts"]), r["station_code"], float(r["h_mm"])) for r in csv.DictReader(f)),
                      key=lambda r: r[0])
    debut = parse(args.debut) if args.debut else rows[0][0]
    fin = parse(args.fin) if args.fin else rows[-1][0]
    offset = datetime.now(timezone.utc) - debut

    producer = Producer(kafka_conf())

    def envoyer(t, code, h):
        msg = {"station_code": code,
               "ts": (t + offset).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "h_mm": h, "source": "replay"}
        producer.produce(KAFKA_TOPIC, key=code, value=json.dumps(msg))
        producer.poll(0)

    # prélude : le contexte juste avant la fenêtre, d'un coup
    for t, code, h in rows:
        if debut.timestamp() - args.prelude_h * 3600 <= t.timestamp() < debut.timestamp():
            envoyer(t, code, h)
    producer.flush()

    # fenêtre : au rythme accéléré
    t0_mur = time.monotonic()
    for t, code, h in rows:
        if not (debut <= t <= fin):
            continue
        attente = (t - debut).total_seconds() / args.speed - (time.monotonic() - t0_mur)
        if attente > 0:
            time.sleep(attente)
        envoyer(t, code, h)
        print(f"[replay] {t:%d/%m %H:%M} {code} {h:.0f} mm")
    producer.flush()


if __name__ == "__main__":
    main()
