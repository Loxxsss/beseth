"""Vérifie les 4 services Aiven et le pipeline Kafka -> ClickHouse. Owner : B.

    python -m ingest.check            # ping Kafka, ClickHouse, PostgreSQL, Valkey
    python -m ingest.check --e2e      # + envoie 1 message test et attend qu'il arrive dans hydro_obs
"""
import argparse
import json
import time
from datetime import datetime, timezone

from config import KAFKA_TOPIC, clickhouse, kafka_conf, postgres, valkey

STATION_TEST = "TEST000000"


def ping_all() -> dict:
    out = {}

    def run(name, fn):
        try:
            out[name] = f"ok ({fn()})"
        except Exception as e:  # on veut voir toutes les erreurs, pas seulement la première
            out[name] = f"ERREUR: {type(e).__name__}: {e}"

    def _kafka():
        from confluent_kafka.admin import AdminClient

        topics = AdminClient(kafka_conf()).list_topics(timeout=15).topics
        return "topics=" + ",".join(sorted(topics))

    def _pg():
        with postgres() as c:
            v = c.execute("SELECT version()").fetchone()[0].split(",")[0]
            postgis = c.execute("SELECT count(*) FROM pg_available_extensions WHERE name='postgis'").fetchone()[0]
            return f"{v}, postgis dispo={bool(postgis)}"

    def _vk():
        r = valkey()
        r.ping()
        try:
            r.execute_command("BF.RESERVE", "sentinelle:bloomtest", 0.01, 100)
            r.delete("sentinelle:bloomtest")
            bloom = True
        except Exception:
            bloom = False
        return f"ping ok, module Bloom={bloom}"

    run("kafka", _kafka)
    run("clickhouse", lambda: "version " + clickhouse().command("SELECT version()"))
    run("postgres", _pg)
    run("valkey", _vk)
    return out


def e2e(timeout_s: int = 60) -> bool:
    from confluent_kafka import Producer

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msg = {"station_code": STATION_TEST, "ts": ts, "h_mm": 1234.0, "source": "hubeau"}
    p = Producer(kafka_conf())
    p.produce(KAFKA_TOPIC, key=STATION_TEST, value=json.dumps(msg))
    p.flush(20)
    print(f"[e2e] envoyé dans Kafka : {msg}")

    ch, t0 = clickhouse(), time.time()
    try:
        while time.time() - t0 < timeout_s:
            n = int(ch.command(f"SELECT count() FROM hydro_obs WHERE station_code = '{STATION_TEST}'"))
            if n:
                print(f"[e2e] reçu dans hydro_obs après {time.time() - t0:.1f} s ✅")
                return True
            time.sleep(2)
        print(f"[e2e] rien dans hydro_obs après {timeout_s} s ❌")
        return False
    finally:
        ch.command(f"ALTER TABLE hydro_obs DELETE WHERE station_code = '{STATION_TEST}'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true")
    a = ap.parse_args()
    for k, v in ping_all().items():
        print(f"{k:11s} {v}")
    if a.e2e:
        e2e()


if __name__ == "__main__":
    main()
