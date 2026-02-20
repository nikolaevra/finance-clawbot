-- ============================================================
-- Add sources JSONB column to messages for document citations
-- ============================================================
-- Stores an array of source references that were used to generate
-- an assistant message (from RAG retrieval or tool calls).
-- Format: [{"source_file": "documents/report.pdf", "score": 0.85}, ...]

alter table messages add column if not exists sources jsonb;

comment on column messages.sources is
  'Array of source references used to generate this assistant message';
