BEGIN;

CREATE TABLE IF NOT EXISTS imbalance_data (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL DEFAULT 'RTE_IMBALANCE',
    import_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT imbalance_data_timestamp_source_unique UNIQUE (timestamp, source)
);

CREATE INDEX IF NOT EXISTS imbalance_data_timestamp_idx
    ON imbalance_data (timestamp);

CREATE TABLE IF NOT EXISTS imbalance_predictions (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    predicted_value DOUBLE PRECISION NOT NULL,
    model_name TEXT NOT NULL,
    horizon TEXT NOT NULL,
    prediction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT imbalance_predictions_timestamp_model_horizon_unique UNIQUE (timestamp, model_name, horizon)
);

CREATE INDEX IF NOT EXISTS imbalance_predictions_timestamp_idx
    ON imbalance_predictions (timestamp);

CREATE INDEX IF NOT EXISTS imbalance_predictions_model_horizon_idx
    ON imbalance_predictions (model_name, horizon);

COMMIT;
