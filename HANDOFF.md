# HANDOFF — Sentinelle Crues (état au 22/10/2026, ~12h35)

Contexte de passation : ce qui tourne, comment le relancer, ce qui reste. **Aucun secret ici** :
les valeurs sont dans le `.env` local de B (jamais commité) et dans les variables des apps Aiven.

## 1. Ce qui tourne

### Services de données (Aiven, projet `berenger-874c`)
| Service | Nom Aiven | Rôle |
| --- | --- | --- |
| Kafka (Inkless, classic topic) | `kafka-3f1fb19` (GCP europe-west2) | topic `hydro.raw`, 3 partitions, auth par certificat client |
| ClickHouse | `clickhouse-1844cf65` (GCP europe-west2) | `default.hydro_obs`, vue matérialisée `hydro_raw_mv`, vues `pente_1h` / `pente_3h` |
| PostgreSQL 18 + PostGIS | `pg-1caa67b5` (DO fra, plan Developer) | sites, emplacements (géolocalisés), seuils, alertes (+ `trace`), sorties |
| Valkey (module Bloom) | `valkey-28feaa16` (DO fra, plan Developer) | anti-doublon des alertes (`alerte:*`) |

Intégration native **Kafka → ClickHouse** : table Kafka-engine `service_kafka-3f1fb19.hydro_raw`
(format JSONEachRow, consumer group `clickhouse-hydro`, config dans `db/clickhouse_kafka_integration.json`).
Latence mesurée Kafka → `hydro_obs` : ~2 s (`python -m ingest.check --e2e`).

### Apps Aiven Runtime (AWS eu-west-1, plan Startup-20-512)
| App | Dockerfile | Ce qu'elle fait |
| --- | --- | --- |
| `api` | `deploy/Dockerfile.api` | FastAPI, port 8000 — **https://01a1630f-d70a-759b-875d-8e5eaac1cb5d-8000.eur-1.aiven.app** (doc : `/docs`) |
| `poller` | `deploy/Dockerfile.poller` | Hub'Eau → Kafka toutes les 2 min (repli auto HydroPortail si Hub'Eau ne répond pas) |
| `agent` | `deploy/Dockerfile.agent` | boucle de l'agent (S), un tour toutes les 20 s (`DEMO_MODE=replay`) — **appelle vraiment `DEMO_PHONE`** sur ALERTE |

Les apps sont construites depuis le **miroir privé `BrgMrg/sentinelle-deploy`** (branche `main`), copie de
`Loxxsss/beseth` : l'app GitHub d'Aiven n'a accès qu'au compte de B.
⚠️ Build context = `/` (racine du repo). Si on recrée une app depuis un Dockerfile, Aiven propose `/deploy` → le build casse sur `COPY requirements.txt`.

### Variables d'environnement des apps (noms seulement)
- Toutes : `KAFKA_BOOTSTRAP`, `KAFKA_CA`, `KAFKA_CERT`, `KAFKA_KEY` (contenu PEM en une ligne avec `\n`, lu par `config.py`),
  `CLICKHOUSE_HOST` (host:port), `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `DATABASE_URL`, `VALKEY_URL`,
  `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_PHONE_NUMBER_ID`, `DEMO_PHONE`, `DEMO_MODE`, `SITE_ID`, `KAFKA_TOPIC`.
- `poller` : + `HYDRO_SOURCE=auto` (`hubeau` | `hydroportail` pour forcer), `RELECTURE_MIN` (défaut 120).
- `agent` : + `ANTHROPIC_API_KEY` (clé « runtime » de S).
- Secrets marqués dans la console : `KAFKA_KEY`, `CLICKHOUSE_PASSWORD`, `DATABASE_URL`, `VALKEY_URL`, `ELEVENLABS_API_KEY`, `ANTHROPIC_API_KEY`.
- Fichier d'import prêt sur le Mac de B : `~/Hackathon/sentinelle-runtime.env` (bouton *Import from file* de la console ; hors repo).

## 2. Redéployer après un merge sur `main`
Depuis `~/Hackathon/beseth` (remote `deploy` = miroir) :
```bash
git fetch origin
git push deploy origin/main:refs/heads/main
```
Puis console Aiven → Runtime → app concernée → **••• → Deploy latest commit** (le push ne redéploie pas seul).
Changement de code API/front → `api` ; ingestion → `poller` ; agent → `agent`. Build ~2-3 min.

## 3. Démo : replay de la crue
```bash
python3 reset_demo.py                    # remise à zéro (S) : alertes, anti-doublon, seuils
python -m ingest.replay                  # crue Ardèche 16/10/2024 08:00→17:00 TU, x180 ≈ 3 min
python -m ingest.replay --purge-only     # après l'essai : supprime les points source='replay'
```
- Ou depuis le front / l'API : `POST /demo/replay`.
- Attendu : Vogüé (V501401001) passe en **ALERTE ~40 s** après le départ (≈ 600 mm, +550 mm/h), A1→A8 menacés,
  appel ElevenLabs vers `DEMO_PHONE`, alerte visible dans `/alertes`.
- Timestamps décalés d'un offset constant (pentes mm/h conservées). Les vues de pente sont calées sur le dernier point
  de chaque station **et sur sa source** : le poller cloud peut continuer à tourner pendant un replay.
- **Ne jamais lancer `agent.loop` en local** pendant que l'app `agent` tourne (double appel).

## 4. Outils de B (`ingest/`)
| Commande | Usage |
| --- | --- |
| `python -m ingest.check --e2e` | ping des 4 services (+ PostGIS, Bloom) + message test Kafka → ClickHouse |
| `python -m ingest.init_pg` | schéma + migrations + seed Postgres, idempotent (rejoue les `UPDATE` du seed) ; `--reseed` = repartir de zéro |
| `python -m ingest.hydroportail --backfill 7` | 7 jours d'historique réel → ClickHouse (HydroPortail, si Hub'Eau bloqué) |
| `python -m ingest.hydroportail --csv f.csv --start 19/10/2026 --end 21/10/2026` | export d'une crue au format replay |
| `python -m ingest.load_csv fichier.csv` | charge un export CSV HydroPortail manuel |
| `python -m ingest.hubeau_poller --dry-run --once` | test du poller sans rien envoyer |

## 5. Faits utiles pour le pitch
- **Vraie crue le 20/10/2026** (données brutes HydroPortail) : Vogüé pic 2 509 mm à 09:30 TU (pente max 557 mm/h),
  Vallon pic 4 091 mm à 10:15 TU, **A1 inondé à 06:45 TU**, A1→A6 touchés.
- Backtest (S) sur octobre 2024 : alerte **6,0 h** avant l'inondation de A1, contre 0,9 h pour un seuil fixe.
- Le réseau du lieu bloque `hubeau.eaufrance.fr` ; Runtime y accède normalement.

## 6. Reste à faire
- [ ] **Front Lovable** (`Loxxsss/pixel-perfect-replay-1095`) : B attend l'accès en lecture (collaborateur `BrgMrg`),
      puis `npm run build` → `dist/` copié dans `web/`, servi par l'app `api` sur la même URL (déjà codé dans `api/main.py`).
      CORS déjà ouverte à `*.aiven.app` et `*.lovable.app`.
- [ ] Redéployer `api` (front + `reset_demo.py` + CORS) une fois le front en place ; vérifier `/`, `/site` (position du camping).
- [ ] Texte du formulaire « The data layer in action » (B) avant 14h45.
- [ ] Répétition complète de la démo sur l'URL publique (reset → replay → appel → `/alertes`).
- [ ] Après le hackathon : **régénérer tous les mots de passe Aiven, la clé Kafka, les clés ElevenLabs et Anthropic**
      (ils ont circulé en messagerie), supprimer les apps Runtime et le miroir `sentinelle-deploy`.
