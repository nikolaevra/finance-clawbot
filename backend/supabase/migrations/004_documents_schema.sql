-- ============================================================
-- Documents: user-uploaded files (PDF, DOCX, XLSX)
-- ============================================================

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  filename text not null,
  file_type text not null,            -- 'pdf', 'docx', 'xlsx'
  file_size bigint not null default 0,
  storage_path text not null,         -- path in Supabase Storage
  extracted_text text,                -- full extracted text content
  status text not null default 'processing'
    check (status in ('processing', 'ready', 'error')),
  created_at timestamptz default now()
);

-- Indexes
create index idx_documents_user on documents(user_id);
create index idx_documents_user_status on documents(user_id, status);

-- Row Level Security
alter table documents enable row level security;

create policy "Users can read own documents"
  on documents for select using (auth.uid() = user_id);

create policy "Users can insert own documents"
  on documents for insert with check (auth.uid() = user_id);

create policy "Users can update own documents"
  on documents for update using (auth.uid() = user_id);

create policy "Users can delete own documents"
  on documents for delete using (auth.uid() = user_id);

-- Service role bypass (for backend operations)
create policy "Service role full access to documents"
  on documents for all using (true) with check (true);
