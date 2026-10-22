# Déploiement sur Aiven Runtime (owner : B)

3 applications, décrites dans `compose.aiven.yaml` :

| app | Dockerfile | rôle |
| --- | --- | --- |
| `api` | `deploy/Dockerfile.api` | FastAPI pour le front Lovable, port 8000 |
| `poller` | `deploy/Dockerfile.poller` | Hub'Eau (repli HydroPortail) → Kafka `hydro.raw`, toutes les 2 min |
| `agent` | `deploy/Dockerfile.agent` | boucle de l'agent (S) |

## Étapes (console Aiven, projet `berenger-874c`)

1. **Runtime → Deploy application → Connect GitHub account.** L'app GitHub d'Aiven doit avoir accès à
   `Loxxsss/beseth` : c'est le propriétaire du repo (S) qui l'autorise.
2. Choisir le repo `beseth`, la branche (`main` après merge), puis le manifeste `compose.aiven.yaml` → **Scan**.
3. Pour chaque app, saisir les **secrets** (mêmes valeurs que le `.env` local) :
   `KAFKA_BOOTSTRAP`, `KAFKA_CA`, `KAFKA_CERT`, `KAFKA_KEY` (contenu PEM collé : `config.py` l'accepte),
   `CLICKHOUSE_HOST` (host:port), `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `DATABASE_URL`, `VALKEY_URL`,
   et pour `agent` : `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`,
   `ELEVENLABS_PHONE_NUMBER_ID`, `DEMO_PHONE`.
4. **Deploy.** Le push GitHub ne redéploie pas tout seul : *Overview → Actions → Deploy latest commit*.

## Pendant une démo en replay
Mettre l'app `poller` en pause (ou `DEMO_MODE=replay` sur l'agent et couper le poller), sinon live et
rejoué se mélangent. Après chaque essai : `python -m ingest.replay --purge-only`.
