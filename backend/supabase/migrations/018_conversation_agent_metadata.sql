-- Conversation metadata for live/background agent history rendering.
ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS conversation_type TEXT NOT NULL DEFAULT 'live'
    CHECK (conversation_type IN ('live', 'background'));

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS agent_mode TEXT NOT NULL DEFAULT 'live'
    CHECK (agent_mode IN ('live', 'background'));

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS agent_source TEXT;

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS agent_run_id TEXT;

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS agent_name TEXT;

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated_mode
  ON conversations (user_id, updated_at DESC, conversation_type, agent_mode);
