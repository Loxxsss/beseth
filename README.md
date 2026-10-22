# Beseth — AI flood alerts for safer river days

**Beseth watches the river gauges upstream of riverside campsites, canoe bases and anyone living or working in a flood-prone area, reasons on how fast the water is rising, and phones the manager hours before the water reaches them.**

Built in one day for the *Future Founders: Data-Centric Agents* challenge (AI Innovate Paris, 22 Oct 2026).

- **Live app:** https://01a1630f-d70a-759b-875d-8e5eaac1cb5d-8000.eur-1.aiven.app/ (API + front on Aiven Runtime)
- **Demo site:** a campsite at Vallon-Pont-d'Arc on the Ardèche, watching two real Hub'Eau gauges: Vallon-Pont-d'Arc (`V505401001`, campsite gauge) and Vogüé (`V501401001`, upstream, ~5 h of propagation).

> Decision support, not a guarantee: people stay in charge.

---

## What it does

1. **Watches live data.** The Hub'Eau real-time river gauges are polled every 2 minutes.
2. **Reasons.** For each gauge it computes the rise rate (1 h and 3 h) and the **ETA for each pitch**, then decides `WATCH / ALERT / CRITICAL`. An upstream gauge gives hours of lead time before the water reaches the site.
3. **Acts.**
   - It **calls the manager** with an ElevenLabs voice agent, *Beseth*.
   - It drafts the **evacuation SMS** for campers. Claude writes the call script and the SMS from the numbers.
   - It **cancels the afternoon canoe trips** when the alert is CRITICAL.
   - It stores the **full reasoning trace** of every decision.
4. **Learns.** After the event, the manager marks the alert as *confirmed* or *false alarm*. On a false alarm, the site's rise threshold is raised (v1 → v2…). Thresholds are learnt **per site, per gauge**.

The decision itself is **deterministic and replayable**, which keeps the backtest honest. The LLM only puts into words a decision already made.

## Data layer (all on Aiven)

```
Hub'Eau (every 2 min) ─┐
                       ├─► Kafka  topic hydro.raw ──(native Aiven integration)──► ClickHouse  hydro_obs
replay of a past flood ┘                                                          views pente_1h / pente_3h
                                                                                         │
                         PostgreSQL + PostGIS ◄──── agent loop (every 20 s–2 min) ◄─────┘
                         sites, geolocated pitches,        │  dedup ──► Valkey (one call per gauge × level)
                         learnt thresholds (versions),     ├──► ElevenLabs outbound call (Beseth)
                         alerts + reasoning trace,         ├──► Claude: call script + evacuation SMS
                         verdicts, canoe trips             └──► API (FastAPI) ──► web front (map, alerts, trips)
```

| Service | What lives there |
| --- | --- |
| **Aiven for Apache Kafka** | `hydro.raw`: every gauge reading, live (`source=hubeau`) or replayed (`source=replay`) |
| **Aiven for ClickHouse** | `hydro_obs` time series and the `pente_1h` / `pente_3h` views, computed on the latest point of each gauge (data time, not wall-clock time, so live and accelerated replay both work) |
| **Aiven for PostgreSQL + PostGIS** | site, geolocated pitches A1–A8, per-site thresholds with versions, alerts with `trace` (JSON reasoning), `call_id`, verdicts, canoe trips |
| **Aiven for Valkey** | anti-duplicate: one call per (site, gauge, level) per 6 h |
| **Aiven Runtime** | three apps: API + front, agent loop, Hub'Eau poller |

Replayed data is always tagged `source=replay` and shown with a **REPLAY** badge in the UI. It is never presented as live.

## Evidence it works — 7 years of real data

We replayed **2019–2025 hourly gauge heights** (Hub'Eau / HydroPortail, Vallon-Pont-d'Arc + Vogüé) through the **same decision code as live**. In that period, **27 floods** reached the first pitch (3 m at Vallon).

| | Fixed threshold (2 m) | Beseth without learning (v1) | **Beseth with the manager's feedback** |
| --- | --- | --- | --- |
| Floods detected | 27/27 | 27/27 | **27/27** |
| Median warning before water reaches the first pitch | 1.0 h | 7.0 h | **3.0 h** |
| False alarms per year | 1.4 | 127 | **2.1** |

How it is measured:
- **Detected** means at least one alert in the 24 h before the water reaches pitch A1. **Warning** is the time between the first such alert and that moment.
- **False alarm** means an alert not followed by water on A1 within 24 h, outside flood episodes. Alerts are counted as calls, with the product's 6 h dedup.
- **With feedback** means that each false alarm is marked by the manager, applied in time order with the same rule as production (`memory.appliquer_verdict`). The early false alarms are counted too.

Being honest about it:
- This is a **historical replay, not live alerts**. Pitch flood heights (3.0–4.4 m) are assumptions for the demo site.
- The best possible fixed threshold for this river (**1.5 m**: 27/27, 3.0 h, 2.1/yr) matches Beseth. We only found it by testing every height on 7 years of floods for this one site, whereas Beseth reaches it from the manager's feedback, and it also acts (call, ETA per pitch, trips cancelled).
- The 2.1/yr is measured on the same 7 years the thresholds learnt from (online learning, in time order).
- The current learning rule only raises thresholds, and over time it erodes the upstream-gauge advantage. On the Oct 2024 flood alone, the upstream gauge gave **6.0 h** of warning versus 0.9 h for the 2 m threshold. Making the learning upstream-aware is the next step.

Reproduce:
```bash
python -m backtest.historique   # 7 years, 27 floods  -> backtest/results_historique.json
python -m backtest.run          # Oct 2024 flood + summer 2024 calm period
```

## Repository layout

```
agent/            decision loop (owner: S)
  decide.py         deterministic decision: rise rate, ETA per pitch, WATCH/ALERT/CRITICAL, upstream logic
  trend.py          reads ClickHouse pente_1h / pente_3h views
  memory.py         Postgres: site context, alerts + trace, verdict -> threshold update
  trace.py          display status + reasoning trace (shared by agent and API)
  dedup.py          Valkey anti-duplicate
  loop.py           the agent loop
  actions/          voice.py (ElevenLabs call), redaction.py (Claude: call + SMS), planning.py (cancel trips)
api/main.py       FastAPI: /stations, /stations/{code}/serie, /site, /alertes, /alertes/{id}/verdict, /demo/replay, /backtest
web/              built front (map, alerts panel, canoe trips, gauge charts)
ingest/           hubeau_poller.py, replay.py, backfill.py, init_pg.py, load_csv.py, hydroportail.py, check.py
db/               postgres.sql, clickhouse.sql, seed_site.sql, migration_*.sql, clickhouse_kafka_integration.json
backtest/         run.py (one flood + calm summer), historique.py (7 years, 27 floods)
data/             crue_ardeche_2024-10.csv (demo replay), calme_ardeche_2024-07-08.csv, historique_ardeche_2019-2025_horaire.csv
deploy/           Dockerfiles for api / agent / poller, RUNTIME.md
reset_demo.py     resets the demo before each run
HANDOFF.md        deployment and operations notes
```

## Run it

```bash
cp .env.example .env            # fill in Aiven, ElevenLabs and Anthropic credentials — never commit .env or certs/
pip install -r requirements.txt
python -m ingest.init_pg        # schema + seed (Postgres)
python -m ingest.hubeau_poller  # live data -> Kafka
python -m agent.loop            # the agent
uvicorn api.main:app            # API + front
```

Deployment on Aiven Runtime is described in `HANDOFF.md` and `deploy/RUNTIME.md`.

## Running the demo

```bash
python reset_demo.py            # thresholds back to v1, replay alerts removed, trips "planned", Valkey cleared, replay data purged
# then ONE replay:
curl -X POST "$API/demo/replay" # or: python -m ingest.replay   (real Oct 2024 flood, 16/10 08:00→17:00 UTC, ×180 ≈ 3 min)
```

What you see:
1. Vogüé turns orange, then red: **ALERT**, and the manager's phone rings.
2. Vallon goes **CRITICAL**, and the canoe trips are cancelled.
3. At the end, *False alarm* on the Vogüé alert moves its rise threshold from v1 to v2.

Run `reset_demo.py` again after each run. Only one agent should be running, and in production that is the cloud one.

## Stack

Python 3.9+, FastAPI, Aiven (Kafka, ClickHouse, PostgreSQL + PostGIS, Valkey, Runtime), Hub'Eau / HydroPortail open data, Claude (Anthropic API) for the call and SMS drafts, ElevenLabs conversational agent + Twilio number for the voice call, Leaflet front.

## Team

| | Role |
| --- | --- |
| **S** — Steve | agent logic, learning, backtest, pitch |
| **T** — Thélio | front, voice agent (ElevenLabs), demo video |
| **B** — Berenger | data layer and infrastructure on Aiven, deployment |

## Next steps

- Automatic onboarding: pull the public gauge history for a new site and calibrate its starting thresholds by replay.
- Upstream-aware learning, so that feedback does not erase the lead time given by upstream gauges.
- Beseth proposes the verdict itself after the ETA by comparing its forecast with what the gauge did, and the manager only validates.
- Real SMS sending, more rivers, rainfall forecasts.
