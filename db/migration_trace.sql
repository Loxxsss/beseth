-- À lancer une fois sur Aiven Postgres (si postgres.sql a déjà été joué) :
-- psql "$DATABASE_URL" -f db/migration_trace.sql
ALTER TABLE alertes ADD COLUMN IF NOT EXISTS trace jsonb;
