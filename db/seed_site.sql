-- Site de démo : camping fictif en bord d'Ardèche à Vallon-Pont-d'Arc.
-- Stations réelles Hub'Eau. Hauteurs d'inondation des emplacements = HYPOTHÈSES
-- (à présenter comme telles au pitch : un vrai gérant les renseigne à l'installation).
INSERT INTO sites (id, nom, type, geom, tel_gerant) VALUES
  (1, 'Camping démo — Vallon-Pont-d''Arc', 'camping', ST_SetSRID(ST_MakePoint(4.398, 44.402), 4326), NULL)
ON CONFLICT DO NOTHING;

-- Vogüé est ~5 h en amont (décalage des pics observé en oct. 2024 : 04h40 -> 09h55 TU)
INSERT INTO site_stations (site_id, station_code, role, delai_propagation_h) VALUES
  (1, 'V505401001', 'reference', 0),   -- L'Ardèche à Vallon-Pont-d'Arc
  (1, 'V501401001', 'amont',     5)    -- L'Ardèche à Vogüé
ON CONFLICT DO NOTHING;

-- Hauteur à Vallon (mm) à partir de laquelle chaque emplacement est touché (hypothèse)
INSERT INTO emplacements (site_id, code, h_inondation_mm) VALUES
  (1, 'A1', 3000), (1, 'A2', 3200), (1, 'A3', 3400), (1, 'A4', 3600),
  (1, 'A5', 3800), (1, 'A6', 4000), (1, 'A7', 4200), (1, 'A8', 4400);

-- Seuils de départ (version 1) ; « fausse alerte » les relève
INSERT INTO seuils (site_id, station_code, pente_alerte_mm_h, h_alerte_mm) VALUES
  (1, 'V505401001', 150, 2500),
  (1, 'V501401001', 150, 2000)
ON CONFLICT DO NOTHING;

INSERT INTO evenements_passes (site_id, date, h_max_mm, note) VALUES
  (1, '2024-10-17', 9230, 'Épisode cévenol, pic à Vallon 9,23 m le 17/10 09h55 TU');

INSERT INTO sorties (site_id, libelle, debut) VALUES
  (1, 'Descente Vallon -> Gorges 14h', date_trunc('day', now()) + interval '14 hours'),
  (1, 'Descente Vallon -> Gorges 16h', date_trunc('day', now()) + interval '16 hours');

-- coords emplacements
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.395778608674264, 44.395815877796245), 4326) WHERE site_id = 1 AND code = 'A1';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.395997683984679, 44.39574282830594), 4326) WHERE site_id = 1 AND code = 'A2';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.396202154274399, 44.395669778724425), 4326) WHERE site_id = 1 AND code = 'A3';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.39664030489523, 44.395534114973984), 4326) WHERE site_id = 1 AND code = 'A4';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.395880843819124, 44.39600371892404), 4326) WHERE site_id = 1 AND code = 'A5';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.396026894026067, 44.39593066966821), 4326) WHERE site_id = 1 AND code = 'A6';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.396172944233011, 44.39588892719536), 4326) WHERE site_id = 1 AND code = 'A7';
UPDATE emplacements SET geom = ST_SetSRID(ST_MakePoint(4.396421229584814, 44.395815877796245), 4326) WHERE site_id = 1 AND code = 'A8';