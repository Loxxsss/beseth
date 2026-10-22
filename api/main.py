"""API FastAPI consommée par le front Lovable. Owner : T (routes) / S (verdict).
Lancer : uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import memory
from config import SITE_ID, clickhouse, postgres

app = FastAPI(title="Sentinelle")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.(lovable\.app|lovableproject\.com)",
    allow_origins=[o for o in [os.getenv("FRONT_ORIGIN_EXACT")] if o],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/stations")
def stations():
    """code, nom, lat, lon, h_now, pente, source, statut pour chaque station du site.
    Fenêtre mesurée sur max(ts) de la station (fonctionne en live et en replay)."""
    from agent.trend import tendances

    ctx = memory.contexte_site(SITE_ID)
    out = []
    for code, t in tendances(list(ctx["stations"])).items():
        seuil = ctx["seuils"].get(code, {})
        pa = seuil.get("pente_alerte_mm_h", 150)
        statut = "alerte" if t.pente_mm_h > pa else "veille" if t.pente_mm_h > 0.5 * pa else "normal"
        out.append({**STATIONS_META.get(code, {"code": code}), "h_now": t.h_now,
                    "pente_mm_h": round(t.pente_mm_h), "source": t.source, "statut": statut,
                    "role": ctx["stations"][code]["role"]})
    return out


STATIONS_META = {
    "V505401001": {"code": "V505401001", "nom": "L'Ardèche à Vallon-Pont-d'Arc", "lat": 44.4005, "lon": 4.3958},
    "V501401001": {"code": "V501401001", "nom": "L'Ardèche à Vogüé", "lat": 44.5524, "lon": 4.4145},
}


@app.get("/stations/{code}/serie")
def serie(code: str, h: int = 24):
    res = clickhouse().query(
        "WITH (SELECT max(ts) FROM hydro_obs WHERE station_code={c:String}) AS t_max "
        "SELECT ts, h_mm, source FROM hydro_obs FINAL WHERE station_code={c:String} "
        "AND ts > t_max - INTERVAL {h:UInt16} HOUR ORDER BY ts",
        parameters={"c": code, "h": h},
    )
    # FINAL : pas de doublon backfill/live ; "Z" : ClickHouse renvoie de l'UTC naïf, sans ça le front décale de 2 h
    return [{"ts": r[0].isoformat() + "Z", "h_mm": r[1], "source": r[2]} for r in res.result_rows]


@app.get("/site")
def site():
    ctx = memory.contexte_site(SITE_ID)
    with postgres() as conn:
        sorties = conn.execute(
            "SELECT id, libelle, debut, statut FROM sorties WHERE site_id=%s ORDER BY debut", (SITE_ID,)
        ).fetchall()
    return {
        "emplacements": [{"code": c, "h_inondation_mm": h} for c, h in ctx["emplacements"]],
        "seuils": ctx["seuils"],
        "sorties": [{"id": s[0], "libelle": s[1], "debut": s[2].isoformat(), "statut": s[3]} for s in sorties],
    }


@app.get("/alertes")
def alertes():
    with postgres() as conn:
        rows = conn.execute(
            """SELECT id, station_code, niveau, h_mm, pente_mm_h, eta_h, emplacements,
                      message, sms, source, verdict, cree_le
               FROM alertes WHERE site_id=%s ORDER BY cree_le DESC LIMIT 50""",
            (SITE_ID,),
        ).fetchall()
    keys = ["id", "station_code", "niveau", "h_mm", "pente_mm_h", "eta_h", "emplacements",
            "message", "sms", "source", "verdict", "cree_le"]
    return [dict(zip(keys, r[:-1] + (r[-1].isoformat(),))) for r in rows]


class Verdict(BaseModel):
    verdict: str  # fausse_alerte | confirmee


@app.post("/alertes/{alerte_id}/verdict")
def verdict(alerte_id: int, body: Verdict):
    if body.verdict not in ("fausse_alerte", "confirmee"):
        raise HTTPException(400, "verdict inconnu")
    return {"nouveau_seuil": memory.appliquer_verdict(alerte_id, body.verdict)}


@app.post("/demo/replay")
def demo_replay():
    # défauts de replay.py : CSV Ardèche, fenêtre 16/10 08:00 -> 17:00 TU, x180
    subprocess.Popen(["python", "-m", "ingest.replay"])
    return {"lance": True}


@app.get("/backtest")
def backtest():
    p = Path("backtest/results.json")
    return json.loads(p.read_text()) if p.exists() else {"status": "pas encore lancé"}
