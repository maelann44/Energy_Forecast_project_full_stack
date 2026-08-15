CREATE TABLE IF NOT EXISTS historical_data (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL DEFAULT 'RTE',
    import_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT historical_data_timestamp_source_unique UNIQUE (timestamp, source)
);

CREATE INDEX IF NOT EXISTS historical_data_timestamp_idx
    ON historical_data (timestamp);

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    predicted_value DOUBLE PRECISION NOT NULL,
    model_name TEXT NOT NULL,
    horizon TEXT NOT NULL,
    prediction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT predictions_timestamp_model_horizon_unique UNIQUE (timestamp, model_name, horizon)
);

CREATE INDEX IF NOT EXISTS predictions_timestamp_idx
    ON predictions (timestamp);

CREATE INDEX IF NOT EXISTS predictions_model_horizon_idx
    ON predictions (model_name, horizon);
