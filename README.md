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
python -m ingest.init_pg              # schéma + seed Postgres (idempotent)
clickhouse-client ... < db/clickhouse.sql
python -m ingest.hubeau_poller        # flux live -> Kafka
python -m agent.loop                  # boucle de l'agent
uvicorn api.main:app --reload         # API
```

Vérifier l'infra : `python -m ingest.check --e2e` (ping des 4 services + message test Kafka → `hydro_obs`).

Démo : couper le poller, puis `DEMO_MODE=replay python -m ingest.replay` (crue Ardèche du 16/10/2024
08:00→17:00 TU à x180, environ 3 min ; badge REPLAY dans le front). Les horodatages sont décalés d'un offset
constant, donc les pentes en mm/h sont celles de la vraie crue ; les vues `pente_1h` / `pente_3h` sont calées sur
le dernier point de chaque station. `python -m ingest.replay --purge-only` efface les points rejoués.

## Équipe

| Qui | Couloir | Branche |
| --- | --- | --- |
| B | données / infra Aiven / Runtime | `b/ingest` |
| T | front Lovable / voix ElevenLabs / vidéo | `t/front-voice` |
| S | agent / backtest / pitch | `s/agent` |

`main` reste déployable. Merge aux syncs : 11h15, 12h30, 13h45. Gel à 14h45.

Aide à la décision, pas une garantie : le gérant garde la main.
