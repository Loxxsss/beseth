"""Remet la démo à zéro avant chaque répétition :  python3 reset_demo.py
- seuils remis en version 1 (valeurs du seed)
- alertes du replay supprimées, verdicts effacés
- sorties canoë remises en « prevue »
- anti-doublon Valkey vidé
- points de replay purgés de ClickHouse
"""
from config import clickhouse, postgres, valkey

SEUILS_V1 = {"V505401001": (150, 2500), "V501401001": (150, 2000)}

with postgres() as c:
    for code, (pente, h) in SEUILS_V1.items():
        c.execute("UPDATE seuils SET pente_alerte_mm_h=%s, h_alerte_mm=%s, version=1, maj_le=now() "
                  "WHERE site_id=1 AND station_code=%s", (pente, h, code))
    n = c.execute("DELETE FROM alertes WHERE source='replay'").rowcount
    c.execute("UPDATE alertes SET verdict=NULL")
    s = c.execute("UPDATE sorties SET statut='prevue' WHERE site_id=1").rowcount
    # sorties toujours à venir : +2 h et +4 h (heure pile), quelle que soit l'heure de la démo
    ids = [r[0] for r in c.execute("SELECT id FROM sorties WHERE site_id=1 ORDER BY id")]
    for i, sid in enumerate(ids):
        c.execute("UPDATE sorties SET debut = date_trunc('hour', now()) + %s * interval '1 hour', "
                  "libelle = regexp_replace(libelle, ' [0-9]+h$', '') WHERE id=%s", (2 + 2 * i, sid))
print(f"Postgres  : seuils v1, {n} alertes replay supprimées, {s} sorties remises en prévue")

v = valkey()
k = v.keys("alerte:*")
for x in k:
    v.delete(x)
print(f"Valkey    : {len(k)} clés anti-doublon supprimées")

clickhouse().command("ALTER TABLE hydro_obs DELETE WHERE source = 'replay'")
print("ClickHouse: points de replay purgés")
print("✅ Démo prête : lancez le replay.")
