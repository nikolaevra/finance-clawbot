-- Workflow templates: pipeline definitions (Lobster-style)
CREATE TABLE IF NOT EXISTS workflow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    steps JSONB NOT NULL DEFAULT '[]',
    schedule TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_templates_name_user
    ON workflow_templates (name, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'));

-- Workflow runs: execution instances
CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    template_id UUID REFERENCES workflow_templates(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    current_step_index INTEGER NOT NULL DEFAULT 0,
    steps_state JSONB NOT NULL DEFAULT '[]',
    resume_token TEXT UNIQUE,
    trigger TEXT NOT NULL DEFAULT 'manual'
        CHECK (trigger IN ('manual', 'chat', 'scheduled')),
    input_args JSONB,
    error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_user_status
    ON workflow_runs (user_id, status);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_resume_token
    ON workflow_runs (resume_token) WHERE resume_token IS NOT NULL;

-- RLS
ALTER TABLE workflow_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;

-- Templates: users see their own + system-wide (user_id IS NULL)
CREATE POLICY workflow_templates_select ON workflow_templates
    FOR SELECT USING (user_id = auth.uid() OR user_id IS NULL);

CREATE POLICY workflow_templates_insert ON workflow_templates
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY workflow_templates_update ON workflow_templates
    FOR UPDATE USING (user_id = auth.uid());

CREATE POLICY workflow_templates_delete ON workflow_templates
    FOR DELETE USING (user_id = auth.uid());

-- Runs: users see only their own
CREATE POLICY workflow_runs_select ON workflow_runs
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY workflow_runs_insert ON workflow_runs
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY workflow_runs_update ON workflow_runs
    FOR UPDATE USING (user_id = auth.uid());

CREATE POLICY workflow_runs_delete ON workflow_runs
    FOR DELETE USING (user_id = auth.uid());

-- Service-role bypass
CREATE POLICY workflow_templates_service ON workflow_templates
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY workflow_runs_service ON workflow_runs
    FOR ALL USING (auth.role() = 'service_role');
