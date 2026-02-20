-- ============================================================
-- Memory Access Log: tracks every memory tool invocation
-- ============================================================

create table if not exists memory_access_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  conversation_id uuid references conversations(id) on delete cascade not null,
  tool_name text not null,          -- 'memory_append', 'memory_read', 'memory_search', 'memory_save'
  source_file text,                 -- e.g. 'daily/2025-02-08.md' or 'MEMORY.md' (null for search)
  created_at timestamptz default now()
);

-- Indexes
create index idx_memory_access_log_user_file on memory_access_log(user_id, source_file);
create index idx_memory_access_log_conversation on memory_access_log(conversation_id);

-- Row Level Security
alter table memory_access_log enable row level security;

create policy "Users can read own memory access logs"
  on memory_access_log for select using (auth.uid() = user_id);

create policy "Service role can insert memory access logs"
  on memory_access_log for insert with check (true);
