-- ============================================================
-- ClickHouse — Sentinelle (owner : B). DÉJÀ APPLIQUÉ sur clickhouse-1844cf65.
-- Pré-requis : intégration native Aiven Kafka -> ClickHouse (config :
-- db/clickhouse_kafka_integration.json). Elle crée la base
-- `service_kafka-3f1fb19` avec la table Kafka-engine `hydro_raw` (topic hydro.raw).
-- ============================================================

-- 1) Stockage des séries (contrat figé)
CREATE TABLE IF NOT EXISTS default.hydro_obs (
    station_code LowCardinality(String),
    ts           DateTime,
    h_mm         Float32,
    source       LowCardinality(String)
) ENGINE = ReplacingMergeTree
ORDER BY (station_code, ts);

-- 2) Kafka -> hydro_obs. ts arrive en ISO 8601 ("2026-10-22T07:40:00Z").
CREATE MATERIALIZED VIEW IF NOT EXISTS default.hydro_raw_mv
TO default.hydro_obs AS
SELECT
    station_code,
    parseDateTimeBestEffort(ts) AS ts,
    toFloat32(h_mm)             AS h_mm,
    source
FROM `service_kafka-3f1fb19`.hydro_raw;

-- 3) & 4) Pentes en mm/h, calées sur le TEMPS DE LA DONNÉE (max(ts) par station),
--    pas sur now() : en replay accéléré, les ts décalés sont dans le futur.
--    En live, max(ts) ≈ now, donc même comportement. (validé avec S)
--    Seuls les points de la même source que le dernier point comptent : sinon, en replay,
--    la fenêtre 3 h mélangeait la crue rejouée et les mesures réelles du jour (pente faussée).
--    À utiliser par agent/trend.py et GET /stations à la place de "ts > now() - ...".
CREATE OR REPLACE VIEW default.pente_1h AS
SELECT o.station_code AS station_code,
       argMax(o.h_mm, o.ts) AS h_now,
       simpleLinearRegression(toUnixTimestamp(o.ts), o.h_mm).1 * 3600 AS pente_mm_h,
       max(o.ts) AS ts_now
FROM default.hydro_obs AS o FINAL
INNER JOIN (SELECT station_code, max(ts) AS tmax, argMax(source, ts) AS src
            FROM default.hydro_obs GROUP BY station_code) AS m
        ON o.station_code = m.station_code
WHERE o.ts > m.tmax - INTERVAL 1 HOUR
  AND o.source = m.src   -- pas de mélange replay / mesures réelles dans la fenêtre
GROUP BY o.station_code;

CREATE OR REPLACE VIEW default.pente_3h AS
SELECT o.station_code AS station_code,
       argMax(o.h_mm, o.ts) AS h_now,
       simpleLinearRegression(toUnixTimestamp(o.ts), o.h_mm).1 * 3600 AS pente_mm_h,
       max(o.ts) AS ts_now
FROM default.hydro_obs AS o FINAL
INNER JOIN (SELECT station_code, max(ts) AS tmax, argMax(source, ts) AS src
            FROM default.hydro_obs GROUP BY station_code) AS m
        ON o.station_code = m.station_code
WHERE o.ts > m.tmax - INTERVAL 3 HOUR
  AND o.source = m.src   -- pas de mélange replay / mesures réelles dans la fenêtre
GROUP BY o.station_code;

-- Vérif rapide :
-- SELECT source, count(), min(ts), max(ts) FROM default.hydro_obs GROUP BY source;
-- SELECT * FROM default.pente_1h;
