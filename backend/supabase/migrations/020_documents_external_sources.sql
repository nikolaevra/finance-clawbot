-- ============================================================
-- Documents: external source metadata (Google Drive links)
-- ============================================================

alter table documents
  add column if not exists source text not null default 'upload'
    check (source in ('upload', 'google_drive')),
  add column if not exists source_external_id text,
  add column if not exists source_web_url text,
  add column if not exists source_version text,
  add column if not exists source_modified_time timestamptz,
  add column if not exists source_checksum text;

create index if not exists idx_documents_user_source
  on documents(user_id, source);

create index if not exists idx_documents_drive_file
  on documents(user_id, source_external_id)
  where source = 'google_drive' and source_external_id is not null;
