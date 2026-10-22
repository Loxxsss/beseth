"""Mémoire par site dans PostgreSQL : seuils, alertes, verdicts. Owner : S."""
from __future__ import annotations

from config import postgres


def contexte_site(site_id: int) -> dict:
    with postgres() as conn:
        stations = conn.execute(
            "SELECT station_code, role, delai_propagation_h FROM site_stations WHERE site_id=%s",
            (site_id,),
        ).fetchall()
        emplacements = conn.execute(
            "SELECT code, h_inondation_mm FROM emplacements WHERE site_id=%s ORDER BY code",
            (site_id,),
        ).fetchall()
        seuils = conn.execute(
            "SELECT station_code, pente_alerte_mm_h, h_alerte_mm, version FROM seuils WHERE site_id=%s",
            (site_id,),
        ).fetchall()
        tel = conn.execute("SELECT tel_gerant FROM sites WHERE id=%s", (site_id,)).fetchone()
    return {
        "stations": {s[0]: {"role": s[1], "delai_h": s[2]} for s in stations},
        "emplacements": emplacements,
        "seuils": {s[0]: {"pente_alerte_mm_h": s[1], "h_alerte_mm": s[2], "version": s[3]} for s in seuils},
        "tel_gerant": tel[0] if tel else None,
    }


def enregistrer_alerte(site_id, station, decision, tendance, message, sms, call_id) -> int:
    with postgres() as conn:
        row = conn.execute(
            """INSERT INTO alertes (site_id, station_code, niveau, h_mm, pente_mm_h, eta_h,
                                    emplacements, message, sms, call_id, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (site_id, station, decision.niveau, tendance.h_now, tendance.pente_mm_h,
             decision.eta_h, decision.emplacements, message, sms, call_id, tendance.source),
        ).fetchone()
    return row[0]


def appliquer_verdict(alerte_id: int, verdict: str) -> dict | None:
    """Sur « fausse alerte » : pente_alerte = 1.2 x pente déclenchante,
    h_alerte = pic observé + 5 %, version + 1. Renvoie le nouveau seuil."""
    with postgres() as conn:
        a = conn.execute(
            "UPDATE alertes SET verdict=%s WHERE id=%s RETURNING site_id, station_code, pente_mm_h, h_mm",
            (verdict, alerte_id),
        ).fetchone()
        if not a or verdict != "fausse_alerte":
            return None
        site_id, station, pente, h = a
        pic = conn.execute(
            "SELECT max(h_mm) FROM alertes WHERE site_id=%s AND station_code=%s AND cree_le > now() - interval '1 day'",
            (site_id, station),
        ).fetchone()[0] or h
        s = conn.execute(
            """UPDATE seuils SET pente_alerte_mm_h = GREATEST(pente_alerte_mm_h, %s * 1.2),
                                 h_alerte_mm = GREATEST(h_alerte_mm, %s * 1.05),
                                 version = version + 1, maj_le = now()
               WHERE site_id=%s AND station_code=%s
               RETURNING pente_alerte_mm_h, h_alerte_mm, version""",
            (pente, pic, site_id, station),
        ).fetchone()
    return {"pente_alerte_mm_h": s[0], "h_alerte_mm": s[1], "version": s[2]}
