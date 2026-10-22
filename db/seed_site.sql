-- Site de démo. Remplacer STATION_REF / STATION_AMONT et les hauteurs
-- une fois la vallée choisie (go/no-go Hub'Eau de 10h30).
INSERT INTO sites (id, nom, type, geom, tel_gerant) VALUES
  (1, 'Camping de démo', 'camping', ST_SetSRID(ST_MakePoint(0, 0), 4326), NULL)
ON CONFLICT DO NOTHING;

INSERT INTO site_stations (site_id, station_code, role, delai_propagation_h) VALUES
  (1, 'STATION_REF',   'reference', 0),
  (1, 'STATION_AMONT', 'amont',     3)
ON CONFLICT DO NOTHING;

INSERT INTO emplacements (site_id, code, h_inondation_mm) VALUES
  (1, 'A1', 2000), (1, 'A2', 2050), (1, 'A3', 2100), (1, 'A4', 2150),
  (1, 'A5', 2200), (1, 'A6', 2250), (1, 'A7', 2300), (1, 'A8', 2350);

INSERT INTO seuils (site_id, station_code, pente_alerte_mm_h, h_alerte_mm) VALUES
  (1, 'STATION_REF',   80, 1800),
  (1, 'STATION_AMONT', 80, 1800)
ON CONFLICT DO NOTHING;

INSERT INTO sorties (site_id, libelle, debut) VALUES
  (1, 'Descente 14h', date_trunc('day', now()) + interval '14 hours'),
  (1, 'Descente 16h', date_trunc('day', now()) + interval '16 hours');
