USE electricity_db;

-- Q1: Average consumption and production per month (trend over time)
SELECT
  DATE_FORMAT(recorded_at, '%Y-%m') AS year_month_,
  ROUND(AVG(consumption), 2) AS avg_consumption,
  ROUND(AVG(production), 2)  AS avg_production
FROM energy_records
GROUP BY DATE_FORMAT(recorded_at, '%Y-%m')
ORDER BY year_month_;

-- Q2: The 5 hours with the highest consumption
SELECT recorded_at, consumption, production
FROM energy_records
ORDER BY consumption DESC
LIMIT 5;

-- Q3: Renewable share of total generation per year (JOIN across all 3 tables)
SELECT
  YEAR(r.recorded_at) AS year,
  ROUND(100 * SUM(CASE WHEN s.is_renewable = 1 THEN g.output_value ELSE 0 END)
        / SUM(g.output_value), 2) AS renewable_share_pct
FROM generation g
JOIN energy_records r ON r.record_id = g.record_id
JOIN energy_sources s ON s.source_id = g.source_id
GROUP BY YEAR(r.recorded_at)
ORDER BY year;

-- Q4: Average consumption by hour of day (daily pattern)
SELECT
  HOUR(recorded_at) AS hour_of_day,
  ROUND(AVG(consumption), 2) AS avg_consumption
FROM energy_records
GROUP BY HOUR(recorded_at)
ORDER BY hour_of_day;