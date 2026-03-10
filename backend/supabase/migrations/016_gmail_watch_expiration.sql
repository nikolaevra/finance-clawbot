ALTER TABLE integrations
    ADD COLUMN IF NOT EXISTS gmail_watch_expiration TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_integrations_gmail_watch_expiration
    ON integrations (provider, status, gmail_watch_expiration);
