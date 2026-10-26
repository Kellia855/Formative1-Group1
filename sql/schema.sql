-- ============================================================
-- Electricity time-series database (MySQL 8+)
-- Dataset: Electricity.csv (hourly, 2019-01-01 to 2024-03-31)
-- ============================================================

CREATE DATABASE IF NOT EXISTS electricity_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE electricity_db;

DROP VIEW  IF EXISTS v_energy_wide;
DROP TABLE IF EXISTS generation;
DROP TABLE IF EXISTS energy_records;
DROP TABLE IF EXISTS energy_sources;

-- 1) Lookup table: one row per generation source
CREATE TABLE energy_sources (
  source_id     TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_name   VARCHAR(30)      NOT NULL,
  is_renewable  BOOLEAN          NOT NULL,
  PRIMARY KEY (source_id),
  UNIQUE KEY uq_source_name (source_name)
) ENGINE=InnoDB;

-- 2) One row per hourly timestamp (totals)
CREATE TABLE energy_records (
  record_id    INT UNSIGNED NOT NULL AUTO_INCREMENT,
  recorded_at  DATETIME     NOT NULL,
  consumption  INT          NOT NULL,
  production   INT          NOT NULL,
  PRIMARY KEY (record_id),
  UNIQUE KEY uq_recorded_at (recorded_at)   -- also serves as the time index
) ENGINE=InnoDB;

-- 3) Generation per source per timestamp (long format)
--    output_value is signed because Wind has small negative readings
CREATE TABLE generation (
  generation_id  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  record_id      INT UNSIGNED     NOT NULL,
  source_id      TINYINT UNSIGNED NOT NULL,
  output_value   INT              NOT NULL,
  PRIMARY KEY (generation_id),
  UNIQUE KEY uq_record_source (record_id, source_id),
  KEY idx_source (source_id),
  CONSTRAINT fk_gen_record FOREIGN KEY (record_id)
    REFERENCES energy_records (record_id) ON DELETE CASCADE,
  CONSTRAINT fk_gen_source FOREIGN KEY (source_id)
    REFERENCES energy_sources (source_id)
) ENGINE=InnoDB;

-- Seed the lookup table (is_renewable is a classification assumption; confirm with the team)
INSERT INTO energy_sources (source_name, is_renewable) VALUES
  ('nuclear',       FALSE),
  ('wind',          TRUE),
  ('hydroelectric', TRUE),
  ('oil_and_gas',   FALSE),
  ('coal',          FALSE),
  ('solar',         TRUE),
  ('biomass',       TRUE);

-- Wide view: one row per timestamp, handy for the API and for Task 4 features
CREATE VIEW v_energy_wide AS
SELECT
  r.record_id,
  r.recorded_at,
  r.consumption,
  r.production,
  MAX(CASE WHEN s.source_name = 'nuclear'       THEN g.output_value END) AS nuclear,
  MAX(CASE WHEN s.source_name = 'wind'          THEN g.output_value END) AS wind,
  MAX(CASE WHEN s.source_name = 'hydroelectric' THEN g.output_value END) AS hydroelectric,
  MAX(CASE WHEN s.source_name = 'oil_and_gas'   THEN g.output_value END) AS oil_and_gas,
  MAX(CASE WHEN s.source_name = 'coal'          THEN g.output_value END) AS coal,
  MAX(CASE WHEN s.source_name = 'solar'         THEN g.output_value END) AS solar,
  MAX(CASE WHEN s.source_name = 'biomass'       THEN g.output_value END) AS biomass
FROM energy_records r
LEFT JOIN generation g     ON g.record_id = r.record_id
LEFT JOIN energy_sources s ON s.source_id = g.source_id
GROUP BY r.record_id, r.recorded_at, r.consumption, r.production;
