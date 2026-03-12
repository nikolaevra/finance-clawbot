-- ============================================================
-- Omnichannel await/resume primitives
-- ============================================================

CREATE TABLE IF NOT EXISTS inbound_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL
        CHECK (channel IN ('email', 'slack', 'whatsapp', 'sms', 'generic')),
    normalized_event_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_waits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'matched', 'expired', 'cancelled')),
    channel TEXT NOT NULL
        CHECK (channel IN ('email', 'slack', 'whatsapp', 'sms', 'generic')),
    wait_type TEXT NOT NULL DEFAULT 'external_response',
    matcher_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    timeout_at TIMESTAMPTZ,
    matched_event_id UUID REFERENCES inbound_events(id) ON DELETE SET NULL,
    matched_payload JSONB,
    skill_name TEXT,
    run_key TEXT,
    tool_call_id TEXT,
    thread_id TEXT,
    channel_ref TEXT,
    phone_number TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_inbound_events_provider_event
    ON inbound_events (provider, provider_event_id);

CREATE INDEX IF NOT EXISTS idx_inbound_events_user_received_at
    ON inbound_events (user_id, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_waits_user_status
    ON automation_waits (user_id, status);

CREATE INDEX IF NOT EXISTS idx_automation_waits_pending_timeout
    ON automation_waits (timeout_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_automation_waits_pending_channel
    ON automation_waits (channel, created_at DESC)
    WHERE status = 'pending';

CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_waits_matched_event
    ON automation_waits (matched_event_id)
    WHERE matched_event_id IS NOT NULL;

ALTER TABLE inbound_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_waits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own inbound events"
    ON inbound_events
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert inbound events"
    ON inbound_events
    FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Users can read own automation waits"
    ON automation_waits
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert automation waits"
    ON automation_waits
    FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service role can update automation waits"
    ON automation_waits
    FOR UPDATE
    USING (true);
