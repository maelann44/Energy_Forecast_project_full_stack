BEGIN;

DELETE FROM predictions p
USING predictions duplicate
WHERE p.timestamp = duplicate.timestamp
  AND p.model_name = duplicate.model_name
  AND p.horizon = duplicate.horizon
  AND p.id < duplicate.id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'predictions_timestamp_model_horizon_unique'
    ) THEN
        ALTER TABLE predictions
        ADD CONSTRAINT predictions_timestamp_model_horizon_unique
        UNIQUE (timestamp, model_name, horizon);
    END IF;
END $$;

COMMIT;
