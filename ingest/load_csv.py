"""Charge des CSV de hauteurs téléchargés à la main (HydroPortail) dans hydro_obs. Owner : B.

Remplace backfill.py quand l'API Hub'Eau n'est pas joignable depuis le réseau du lieu.

    python -m ingest.load_csv data/V505401001.csv --station V505401001
    python -m ingest.load_csv data/*.csv                 # code station lu dans le nom de fichier
    python -m ingest.load_csv data/x.csv --dry-run       # affiche ce qui serait chargé
    python -m ingest.load_csv data/x.csv --kafka         # passe par Kafka au lieu d'écrire direct

Formats acceptés (détection automatique) :
- format du repo : station_code,ts,h_mm
- export HydroPortail : séparateur ; ou , ; une colonne de date (« Date (TU) », « Date »…),
  une colonne de valeur (« Valeur (en mm) », « Valeur »…) ; en-têtes éventuels avant le tableau.
Les points sont marqués source="hubeau" (ce sont de vraies mesures, pas un replay).
"""
import argparse
import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CODE_RE = re.compile(r"[A-Z]\d{9}")


def _parse_ts(s: str) -> datetime:
    s = s.strip().strip('"')
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _float(s: str) -> float | None:
    s = s.strip().strip('"').replace(" ", "").replace(" ", "")
    if not s:
        return None
    if s.count(",") == 1 and "." not in s:  # décimale française
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def lire(path: Path, station: str | None = None) -> tuple[list[tuple[str, datetime, float]], str]:
    """Retourne [(station_code, ts UTC, h_mm)] et une description du format détecté."""
    texte = path.read_text(encoding="utf-8-sig", errors="replace")
    lignes = texte.splitlines()
    sep = ";" if texte.count(";") > texte.count(",") / 2 else ","

    # trouve la ligne d'en-tête du tableau (HydroPortail met parfois des métadonnées avant)
    i_head = next(
        (i for i, l in enumerate(lignes) if re.search(r"(?i)\b(date|ts)\b", l) and sep in l), 0
    )
    reader = csv.reader(io.StringIO("\n".join(lignes[i_head:])), delimiter=sep)
    head = [h.strip().lower() for h in next(reader)]

    def col(*motifs):
        for m in motifs:
            for j, h in enumerate(head):
                if re.search(m, h):
                    return j
        return None

    j_code = col(r"^station_code$", r"code.*(station|entit|site)")
    j_ts = col(r"^ts$", r"date")
    j_h = col(r"^h_mm$", r"valeur", r"hauteur", r"^h\b", r"r[ée]sultat")
    if j_ts is None or j_h is None:
        raise ValueError(f"{path.name} : colonnes date/valeur introuvables dans {head}")

    defaut = station or (CODE_RE.search(path.name) or CODE_RE.search(texte[:2000]) or [None])[0]
    unite_m = bool(re.search(r"\(\s*m\s*\)|en m\b", head[j_h]))  # export en mètres -> mm

    rows = []
    for r in reader:
        if len(r) <= max(j_ts, j_h):
            continue
        h = _float(r[j_h])
        code = (r[j_code].strip() if j_code is not None and r[j_code].strip() else defaut)
        if h is None or not code:
            continue
        try:
            ts = _parse_ts(r[j_ts])
        except ValueError:
            continue
        rows.append((code, ts, h * 1000 if unite_m else h))
    if rows and not defaut and j_code is None:
        raise ValueError(f"{path.name} : code station introuvable, utiliser --station")
    fmt = f"sep='{sep}', date='{head[j_ts]}', valeur='{head[j_h]}'" + (" (m→mm)" if unite_m else "")
    return sorted(rows, key=lambda x: (x[0], x[1])), fmt


def charger(rows, mode: str):
    if mode == "kafka":
        from confluent_kafka import Producer

        from config import KAFKA_TOPIC, kafka_conf

        p = Producer(kafka_conf())
        for code, ts, h in rows:
            m = {"station_code": code, "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "h_mm": h, "source": "hubeau"}
            p.produce(KAFKA_TOPIC, key=code, value=json.dumps(m))
            p.poll(0)
        p.flush(30)
    else:
        from config import clickhouse

        clickhouse().insert(
            "hydro_obs",
            [[c, ts.replace(tzinfo=None), h, "hubeau"] for c, ts, h in rows],
            column_names=["station_code", "ts", "h_mm", "source"],
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fichiers", nargs="+", type=Path)
    ap.add_argument("--station", help="code station si absent du fichier et du nom de fichier")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--kafka", action="store_true", help="passer par Kafka plutôt qu'écrire direct")
    a = ap.parse_args()

    for f in a.fichiers:
        rows, fmt = lire(f, a.station)
        if not rows:
            print(f"[load_csv] {f.name} : aucune mesure lue ({fmt})")
            continue
        par_station = {}
        for c, ts, h in rows:
            par_station.setdefault(c, []).append((ts, h))
        for c, pts in par_station.items():
            print(f"[load_csv] {f.name} : {c} {len(pts)} mesures {pts[0][0]:%d/%m %H:%M} → "
                  f"{pts[-1][0]:%d/%m %H:%M} TU, {min(h for _, h in pts):.0f}–{max(h for _, h in pts):.0f} mm  [{fmt}]")
        if not a.dry_run:
            charger(rows, "kafka" if a.kafka else "direct")
            print(f"[load_csv] {f.name} : chargé ✅")


if __name__ == "__main__":
    main()
