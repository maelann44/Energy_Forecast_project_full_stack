BEGIN;

TRUNCATE TABLE historical_data RESTART IDENTITY;

CREATE TEMP TABLE tmp_consumption_hourly (
    start_date TEXT,
    date_column TEXT,
    hour_column INTEGER,
    avg_value_hourly DOUBLE PRECISION
);

COPY tmp_consumption_hourly
FROM '/tmp/consumption_data_avg_hourly.csv'
WITH (FORMAT csv, HEADER true);

INSERT INTO historical_data (timestamp, value, source)
SELECT
    start_date::TIMESTAMPTZ AS timestamp,
    avg_value_hourly AS value,
    'RTE' AS source
FROM tmp_consumption_hourly
WHERE start_date::TIMESTAMPTZ >= '2024-01-01 00:00:00+00'::TIMESTAMPTZ
  AND start_date::TIMESTAMPTZ < '2025-01-01 00:00:00+00'::TIMESTAMPTZ
  AND avg_value_hourly IS NOT NULL
ON CONFLICT (timestamp, source)
DO UPDATE SET
    value = EXCLUDED.value,
    import_date = NOW();

COMMIT;
