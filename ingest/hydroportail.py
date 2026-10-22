"""Source de repli : HydroPortail (hydro.eaufrance.fr) quand l'API Hub'Eau est bloquée. Owner : B.

Même producteur Vigicrues que Hub'Eau, mêmes mesures (H en mm, pas de 5 min, données brutes),
lues sur l'endpoint qu'utilise la page « Série de mesures » du site. Endpoint non documenté :
à réserver au repli, Hub'Eau reste la source officielle.

    python -m ingest.hydroportail --live                  # poller -> Kafka toutes les 2 min (comme hubeau_poller)
    python -m ingest.hydroportail --backfill 7            # 7 derniers jours -> ClickHouse (remplace backfill.py)
    python -m ingest.hydroportail --csv data/crue_ardeche_2026-10-20.csv --start 19/10/2026 --end 21/10/2026
    python -m ingest.hydroportail --live --dry-run        # affiche, n'envoie rien
"""
import argparse
import csv
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from ingest.hubeau_poller import PERIODE_S, envoyeur, nouveaux, stations_du_site

URL = "https://www.hydro.eaufrance.fr/stationhydro/ajax/{code}/series"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0 (Sentinelle hackathon)"}


def fetch(code: str, debut: datetime, fin: datetime, client: httpx.Client | None = None) -> list[dict]:
    """Observations au format Hub'Eau ({code_station, date_obs, resultat_obs}) entre deux dates (jours inclus)."""
    params = {
        "hydro_series[startAt]": debut.strftime("%d/%m/%Y"),
        "hydro_series[endAt]": fin.strftime("%d/%m/%Y"),
        "hydro_series[variableType]": "simple_and_interpolated_and_hourly_variable",
        "hydro_series[simpleAndInterpolatedAndHourlyVariable]": "H",
        "hydro_series[statusData]": "raw",
    }
    c = client or httpx.Client(timeout=60, headers=HEADERS, follow_redirects=True)
    r = c.get(URL.format(code=code), params=params)
    r.raise_for_status()
    serie = r.json()["series"]
    if serie.get("unit", "mm") != "mm":
        raise RuntimeError(f"{code} : unité inattendue {serie.get('unit')}")
    return [
        {"code_station": code, "date_obs": p["t"], "resultat_obs": p["v"]}
        for p in serie.get("data", [])
        if p.get("v") is not None
    ]


def fetch_all(stations, debut, fin) -> list[dict]:
    with httpx.Client(timeout=60, headers=HEADERS, follow_redirects=True) as c:
        return [o for code in stations for o in fetch(code, debut, fin, c)]


def live(stations, mode):
    send, dernier_ts = envoyeur(mode), {}
    print(f"[hydroportail] live {stations}, mode={mode}, toutes les {PERIODE_S}s")
    while True:
        t0 = time.time()
        try:
            now = datetime.now(timezone.utc)
            # fenêtre hier→aujourd'hui (le site raisonne en jours) ; le 1er passage envoie donc ~24-48 h,
            # puis seules les nouvelles mesures partent (hydro_obs est un ReplacingMergeTree : pas de doublon)
            msgs = nouveaux(fetch_all(stations, now - timedelta(days=1), now), dernier_ts)
            if msgs:
                send(msgs)
            print(f"[hydroportail] {datetime.now():%H:%M:%S} {len(msgs)} nouvelles mesures"
                  + (f", dernière {max(m['ts'] for m in msgs)}" if msgs else ""))
        except Exception as e:  # la boucle ne meurt jamais
            print(f"[hydroportail] ERREUR {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(max(0, PERIODE_S - (time.time() - t0)))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true", help="poller continu")
    g.add_argument("--backfill", type=int, metavar="JOURS", help="charge les N derniers jours")
    g.add_argument("--csv", help="exporte au format du repo (station_code,ts,h_mm) pour le replay")
    ap.add_argument("--start", help="dd/mm/yyyy (avec --csv)")
    ap.add_argument("--end", help="dd/mm/yyyy (avec --csv)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--kafka", action="store_true", help="--backfill via Kafka au lieu d'écrire direct")
    a = ap.parse_args()

    stations = stations_du_site()
    if a.live:
        return live(stations, "dry" if a.dry_run else "kafka")

    now = datetime.now(timezone.utc)
    if a.csv:
        debut = datetime.strptime(a.start, "%d/%m/%Y") if a.start else now - timedelta(days=7)
        fin = datetime.strptime(a.end, "%d/%m/%Y") if a.end else now
    else:
        debut, fin = now - timedelta(days=a.backfill), now
    obs = fetch_all(stations, debut, fin)
    for code in stations:
        pts = [o for o in obs if o["code_station"] == code]
        if pts:
            vs = [o["resultat_obs"] for o in pts]
            print(f"[hydroportail] {code} : {len(pts)} mesures {pts[0]['date_obs']} → {pts[-1]['date_obs']}, "
                  f"{min(vs):.0f}–{max(vs):.0f} mm")
        else:
            print(f"[hydroportail] {code} : aucune mesure")

    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["station_code", "ts", "h_mm"])
            for o in sorted(obs, key=lambda o: o["date_obs"]):
                w.writerow([o["code_station"], o["date_obs"], o["resultat_obs"]])
        print(f"[hydroportail] écrit {a.csv}")
    elif not a.dry_run:
        msgs = nouveaux(obs, {})
        envoyeur("kafka" if a.kafka else "direct")(msgs)
        print(f"[hydroportail] {len(msgs)} mesures chargées ✅")


if __name__ == "__main__":
    main()
