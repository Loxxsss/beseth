-- Table cible de l'intégration native Aiven Kafka -> ClickHouse (topic hydro.raw).
-- Si l'intégration est configurée côté Aiven, elle crée une table Kafka-engine ;
-- on y branche une vue matérialisée vers hydro_obs.
CREATE TABLE IF NOT EXISTS hydro_obs (
  station_code LowCardinality(String),
  ts           DateTime,
  h_mm         Float32,
  source       LowCardinality(String)
) ENGINE = ReplacingMergeTree
ORDER BY (station_code, ts);

-- Pente sur la dernière heure, en mm/h (utilisée par agent/trend.py)
-- SELECT station_code,
--        argMax(h_mm, ts) AS h_now,
--        simpleLinearRegression(toUnixTimestamp(ts), h_mm).1 * 3600 AS pente_mm_h
-- FROM hydro_obs
-- WHERE ts > now() - INTERVAL 1 HOUR
-- GROUP BY station_code;
