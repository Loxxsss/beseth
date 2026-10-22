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
    """code, h_now, pente, source pour chaque station du site (lat/lon : à ajouter via Hub'Eau référentiel)."""
    ch = clickhouse()
    res = ch.query(
        """SELECT station_code, argMax(h_mm, ts), argMax(source, ts),
                  simpleLinearRegression(toUnixTimestamp(ts), h_mm).1 * 3600
           FROM hydro_obs WHERE ts > now() - INTERVAL 1 HOUR GROUP BY station_code"""
    )
    return [
        {"code": r[0], "h_now": r[1], "source": r[2], "pente_mm_h": r[3]}
        for r in res.result_rows
    ]


@app.get("/stations/{code}/serie")
def serie(code: str, h: int = 24):
    res = clickhouse().query(
        "SELECT ts, h_mm, source FROM hydro_obs WHERE station_code={c:String} "
        "AND ts > now() - INTERVAL {h:UInt16} HOUR ORDER BY ts",
        parameters={"c": code, "h": h},
    )
    return [{"ts": r[0].isoformat(), "h_mm": r[1], "source": r[2]} for r in res.result_rows]


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
def demo_replay(csv: str = "data/crue.csv", speed: float = 60):
    subprocess.Popen(["python", "-m", "ingest.replay", "--csv", csv, "--speed", str(speed)])
    return {"lance": True}


@app.get("/backtest")
def backtest():
    p = Path("backtest/results.json")
    return json.loads(p.read_text()) if p.exists() else {"status": "pas encore lancé"}
