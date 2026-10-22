CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS sites (
  id          serial PRIMARY KEY,
  nom         text NOT NULL,
  type        text NOT NULL CHECK (type IN ('camping', 'club')),
  geom        geometry(Point, 4326),
  tel_gerant  text
);

-- h_inondation_mm : hauteur à la station de référence qui inonde l'emplacement
CREATE TABLE IF NOT EXISTS emplacements (
  id               serial PRIMARY KEY,
  site_id          int REFERENCES sites(id),
  code             text NOT NULL,
  geom             geometry(Point, 4326),
  h_inondation_mm  real NOT NULL
);

CREATE TABLE IF NOT EXISTS site_stations (
  site_id               int REFERENCES sites(id),
  station_code          text NOT NULL,
  role                  text NOT NULL CHECK (role IN ('amont', 'reference')),
  delai_propagation_h   real NOT NULL DEFAULT 0,
  PRIMARY KEY (site_id, station_code)
);

-- la mémoire qui s'ajuste après chaque « fausse alerte »
CREATE TABLE IF NOT EXISTS seuils (
  site_id            int REFERENCES sites(id),
  station_code       text NOT NULL,
  pente_alerte_mm_h  real NOT NULL,
  h_alerte_mm        real NOT NULL,
  version            int NOT NULL DEFAULT 1,
  maj_le             timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (site_id, station_code)
);

CREATE TABLE IF NOT EXISTS evenements_passes (
  id        serial PRIMARY KEY,
  site_id   int REFERENCES sites(id),
  date      date NOT NULL,
  h_max_mm  real NOT NULL,
  note      text
);

CREATE TABLE IF NOT EXISTS alertes (
  id            serial PRIMARY KEY,
  site_id       int REFERENCES sites(id),
  station_code  text NOT NULL,
  niveau        text NOT NULL CHECK (niveau IN ('VEILLE', 'ALERTE', 'CRITIQUE')),
  h_mm          real,
  pente_mm_h    real,
  eta_h         real,
  emplacements  text[],
  message       text,
  sms           text,
  call_id       text,
  source        text NOT NULL DEFAULT 'hubeau',   -- hubeau | replay
  trace         jsonb,                            -- chiffres qui ont motivé la décision (affichés par le front)
  verdict       text CHECK (verdict IN ('fausse_alerte', 'confirmee')),
  cree_le       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sorties (
  id       serial PRIMARY KEY,
  site_id  int REFERENCES sites(id),
  libelle  text,
  debut    timestamptz NOT NULL,
  statut   text NOT NULL DEFAULT 'prevue' CHECK (statut IN ('prevue', 'annulee'))
);
