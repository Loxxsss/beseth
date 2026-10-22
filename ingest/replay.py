"""Rejoue une crue passée dans le même pipeline que le live (Kafka hydro.raw). Owner : B.

    python -m ingest.replay                        # fenêtre démo, x180 (~3 min)
    python -m ingest.replay --start 2024-10-16T08:00:00Z --end 2024-10-16T17:00:00Z --speed 180
    python -m ingest.replay --dry-run --no-sleep   # affiche, n'envoie rien, sans attendre
    python -m ingest.replay --direct               # plan B : ClickHouse sans Kafka
    python -m ingest.replay --purge-only           # supprime les points replay

CSV : station_code,ts,h_mm (ts ISO UTC). Les messages portent source="replay" (badge REPLAY).

Règles (validées avec S) :
- offset CONSTANT : ts_rejoué = ts_origine + (now - début de fenêtre). L'écart entre
  points est conservé, donc les pentes en mm/h aussi, quelle que soit la vitesse.
- En accéléré, les ts rejoués passent dans le futur : les vues pente_1h / pente_3h
  (db/clickhouse.sql) sont calées sur max(ts) de chaque station, pas sur now().
- Les anciens points source='replay' sont purgés avant chaque replay.
- Couper le poller live pendant un replay (DEMO_MODE=replay).
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from config import KAFKA_TOPIC

CSV_DEFAUT = Path(__file__).resolve().parent.parent / "data" / "crue_ardeche_2024-10.csv"
DEMO_DEBUT = "2024-10-16T08:00:00Z"  # Vogüé passe en ALERTE vers 10:05 (~40 s à x180)
DEMO_FIN = "2024-10-16T17:00:00Z"    # A1 touché à Vallon à 16:05


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00").replace(" ", "T"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def charger(csv_path, debut: datetime, fin: datetime) -> list[tuple[datetime, str, float]]:
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r["ts"])
            if debut <= ts <= fin and r.get("h_mm") not in (None, ""):
                rows.append((ts, r["station_code"].strip(), float(r["h_mm"])))
    rows.sort()
    return rows


def purger_replay():
    from config import clickhouse

    clickhouse().command(
        "ALTER TABLE hydro_obs DELETE WHERE source = 'replay'", settings={"mutations_sync": 2}
    )


def run(debut: str = DEMO_DEBUT, fin: str = DEMO_FIN, speed: float = 180, mode: str = "kafka",
        csv_path=CSV_DEFAUT, attendre: bool = True, purger: bool = True, log=print) -> int:
    """Lance le replay (réutilisable depuis l'API). Retourne le nombre de points envoyés."""
    t_debut, t_fin = parse_ts(debut), parse_ts(fin)
    rows = charger(csv_path, t_debut, t_fin)
    if not rows:
        raise ValueError(f"aucun point entre {debut} et {fin} dans {csv_path}")

    if purger and mode != "dry":
        purger_replay()
        log("[replay] anciens points replay purgés")

    offset = datetime.now(timezone.utc) - t_debut
    duree = (t_fin - t_debut).total_seconds() / speed
    log(f"[replay] {len(rows)} points, {debut} → {fin}, x{speed:g} (~{duree / 60:.1f} min), mode={mode}")

    send, flush = None, lambda: None
    if mode == "kafka":
        from confluent_kafka import Producer

        from config import kafka_conf

        producer = Producer(kafka_conf())

        def send(m):
            producer.produce(KAFKA_TOPIC, key=m["station_code"], value=json.dumps(m))
            producer.poll(0)

        flush = lambda: producer.flush(20)
    elif mode == "direct":
        from config import clickhouse

        ch = clickhouse()
        send = lambda m: ch.insert(
            "hydro_obs", [[m["station_code"], parse_ts(m["ts"]).replace(tzinfo=None), m["h_mm"], m["source"]]],
            column_names=["station_code", "ts", "h_mm", "source"])

    t0 = time.time()
    for ts, code, h in rows:
        if attendre:  # cale le temps réel sur le temps de la donnée divisé par speed
            time.sleep(max(0.0, t0 + (ts - t_debut).total_seconds() / speed - time.time()))
        m = {"station_code": code, "ts": fmt(ts + offset), "h_mm": h, "source": "replay"}
        if send:
            send(m)
            if mode == "kafka" and attendre:
                flush()  # en démo, chaque point doit arriver tout de suite
        if mode == "dry" or ts.minute % 30 == 0:
            log(f"[replay] {fmt(ts)} (origine) → {m['ts']}  {code}  {h:.0f} mm")
    flush()
    log(f"[replay] terminé : {len(rows)} points envoyés")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CSV_DEFAUT)
    ap.add_argument("--start", default=DEMO_DEBUT)
    ap.add_argument("--end", default=DEMO_FIN)
    ap.add_argument("--speed", type=float, default=180)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--direct", action="store_true", help="plan B : ClickHouse sans Kafka")
    ap.add_argument("--no-sleep", action="store_true", help="envoie tout d'un coup (tests)")
    ap.add_argument("--purge-only", action="store_true")
    a = ap.parse_args()

    if a.purge_only:
        purger_replay()
        print("[replay] points replay supprimés")
        return
    mode = "dry" if a.dry_run else "direct" if a.direct else "kafka"
    run(a.start, a.end, a.speed, mode, a.csv, attendre=not a.no_sleep)


if __name__ == "__main__":
    main()
