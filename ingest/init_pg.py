"""Crée le schéma PostgreSQL (db/postgres.sql) et seed le site de démo (db/seed_site.sql). Owner : B.

    python -m ingest.init_pg            # idempotent : le seed n'est joué que si le site n'existe pas
    python -m ingest.init_pg --reseed   # vide les données de démo et rejoue le seed (garde le schéma)

Remplace `psql -f db/postgres.sql -f db/seed_site.sql` (psql n'est pas installé partout).
"""
import argparse
from pathlib import Path

from config import SITE_ID, postgres

DB = Path(__file__).resolve().parent.parent / "db"
TABLES_DEMO = ["alertes", "sorties", "evenements_passes", "seuils", "emplacements", "site_stations", "sites"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reseed", action="store_true")
    a = ap.parse_args()

    with postgres() as conn:
        conn.execute((DB / "postgres.sql").read_text())
        print("[init_pg] schéma OK (postgres.sql)")

        if a.reseed:
            conn.execute(f"TRUNCATE {', '.join(TABLES_DEMO)} RESTART IDENTITY CASCADE")
            print("[init_pg] données de démo vidées")

        if conn.execute("SELECT 1 FROM sites WHERE id = %s", (SITE_ID,)).fetchone():
            print(f"[init_pg] site {SITE_ID} déjà présent : seed ignoré (--reseed pour le rejouer)")
        else:
            conn.execute((DB / "seed_site.sql").read_text())
            # le seed insère sites.id=1 explicitement : on recale la séquence
            conn.execute("SELECT setval(pg_get_serial_sequence('sites','id'), (SELECT max(id) FROM sites))")
            print("[init_pg] seed OK (seed_site.sql)")

        for t in TABLES_DEMO[::-1]:
            n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  {t:18s} {n}")
        st = conn.execute(
            "SELECT station_code, role, delai_propagation_h FROM site_stations WHERE site_id=%s ORDER BY role DESC",
            (SITE_ID,),
        ).fetchall()
        print("  stations du site :", ", ".join(f"{c} ({r}, {d:g} h)" for c, r, d in st))


if __name__ == "__main__":
    main()
