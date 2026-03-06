-- Skills metadata table: lightweight index for fast listing.
-- Actual skill content (SKILL.md) lives in Supabase Storage.
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_skills_user_enabled
    ON skills (user_id, enabled);

-- RLS
ALTER TABLE skills ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS skills_select ON skills;
CREATE POLICY skills_select ON skills
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS skills_insert ON skills;
CREATE POLICY skills_insert ON skills
    FOR INSERT WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS skills_update ON skills;
CREATE POLICY skills_update ON skills
    FOR UPDATE USING (user_id = auth.uid());

DROP POLICY IF EXISTS skills_delete ON skills;
CREATE POLICY skills_delete ON skills
    FOR DELETE USING (user_id = auth.uid());

-- Service-role bypass
DROP POLICY IF EXISTS skills_service ON skills;
CREATE POLICY skills_service ON skills
    FOR ALL USING (auth.role() = 'service_role');
