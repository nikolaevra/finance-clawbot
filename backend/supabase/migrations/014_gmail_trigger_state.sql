-- Persist Gmail webhook cursor/profile data per integration.
ALTER TABLE integrations
    ADD COLUMN IF NOT EXISTS gmail_email TEXT,
    ADD COLUMN IF NOT EXISTS gmail_history_id TEXT;

CREATE INDEX IF NOT EXISTS idx_integrations_provider_gmail_email
    ON integrations (provider, gmail_email)
    WHERE provider = 'gmail';
