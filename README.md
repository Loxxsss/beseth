# Sentinelle — alerte crues pour campings et bases de canoë

L'agent surveille les stations Hub'Eau en amont d'un site, calcule la vitesse de montée,
appelle le gérant (ElevenLabs), rédige le SMS d'évacuation et annule les sorties canoë.
Le verdict « fausse alerte » ajuste le seuil du site (mémoire Postgres).

## Architecture

Hub'Eau (2 min) / replay.py → Kafka `hydro.raw` → ClickHouse (séries, pente)
→ agent (tendance → ETA → décision) ↔ PostgreSQL+PostGIS (sites, seuils, alertes) ↔ Valkey (dédoublonnage)
→ appel ElevenLabs · SMS · planning · API FastAPI → front Lovable (repo séparé `sentinelle-crues-web`).

Tout est sur Aiven ; API + workers déployés sur Aiven Runtime.

## Lancer en local

```bash
cp .env.example .env          # remplir les valeurs (jamais commité)
pip install -r requirements.txt
psql "$DATABASE_URL" -f db/postgres.sql -f db/seed_site.sql
clickhouse-client ... < db/clickhouse.sql
python -m ingest.hubeau_poller        # flux live -> Kafka
python -m agent.loop                  # boucle de l'agent
uvicorn api.main:app --reload         # API
```

Démo : `DEMO_MODE=replay python -m ingest.replay --csv data/crue.csv` (badge REPLAY dans le front).

## Équipe

| Qui | Couloir | Branche |
| --- | --- | --- |
| B | données / infra Aiven / Runtime | `b/ingest` |
| T | front Lovable / voix ElevenLabs / vidéo | `t/front-voice` |
| S | agent / backtest / pitch | `s/agent` |

`main` reste déployable. Merge aux syncs : 11h15, 12h30, 13h45. Gel à 14h45.

Aide à la décision, pas une garantie : le gérant garde la main.
