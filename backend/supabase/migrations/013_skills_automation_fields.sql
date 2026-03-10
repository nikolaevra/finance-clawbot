-- Extend skills metadata with automation scheduling + trigger configuration.
ALTER TABLE skills
    ADD COLUMN IF NOT EXISTS schedule_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS schedule_type TEXT,
    ADD COLUMN IF NOT EXISTS schedule_days SMALLINT[],
    ADD COLUMN IF NOT EXISTS schedule_time TEXT,
    ADD COLUMN IF NOT EXISTS schedule_timezone TEXT,
    ADD COLUMN IF NOT EXISTS last_scheduled_run_key TEXT,
    ADD COLUMN IF NOT EXISTS trigger_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS trigger_provider TEXT,
    ADD COLUMN IF NOT EXISTS trigger_event TEXT,
    ADD COLUMN IF NOT EXISTS trigger_filters JSONB,
    ADD COLUMN IF NOT EXISTS last_trigger_event_key TEXT;

ALTER TABLE skills
    DROP CONSTRAINT IF EXISTS skills_schedule_type_check,
    ADD CONSTRAINT skills_schedule_type_check
        CHECK (schedule_type IS NULL OR schedule_type IN ('daily', 'weekly'));

ALTER TABLE skills
    DROP CONSTRAINT IF EXISTS skills_schedule_time_check,
    ADD CONSTRAINT skills_schedule_time_check
        CHECK (schedule_time IS NULL OR schedule_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$');

ALTER TABLE skills
    DROP CONSTRAINT IF EXISTS skills_trigger_provider_check,
    ADD CONSTRAINT skills_trigger_provider_check
        CHECK (trigger_provider IS NULL OR trigger_provider IN ('gmail'));

ALTER TABLE skills
    DROP CONSTRAINT IF EXISTS skills_trigger_event_check,
    ADD CONSTRAINT skills_trigger_event_check
        CHECK (trigger_event IS NULL OR trigger_event IN ('new_email'));

ALTER TABLE skills
    ALTER COLUMN trigger_filters SET DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_skills_user_schedule_enabled
    ON skills (user_id, schedule_enabled);

CREATE INDEX IF NOT EXISTS idx_skills_user_trigger_enabled
    ON skills (user_id, trigger_enabled);
