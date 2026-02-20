-- ============================================================
-- Finance Assistant: Initial Database Schema
-- ============================================================

-- Conversations
create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  title text not null default 'New Chat',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_conversations_user_id on conversations(user_id);
create index idx_conversations_updated_at on conversations(updated_at desc);

-- Messages
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete cascade not null,
  role text not null check (role in ('user', 'assistant', 'system', 'tool')),
  content text,
  tool_calls jsonb,
  tool_call_id text,
  model text,
  thinking text,
  created_at timestamptz default now()
);

create index idx_messages_conversation_id on messages(conversation_id);
create index idx_messages_created_at on messages(conversation_id, created_at);

-- Row Level Security
alter table conversations enable row level security;
alter table messages enable row level security;

create policy "Users can manage own conversations"
  on conversations for all using (auth.uid() = user_id);

create policy "Users can manage messages in own conversations"
  on messages for all using (
    conversation_id in (
      select id from conversations where user_id = auth.uid()
    )
  );

-- Auto-update updated_at on conversations
create or replace function update_updated_at_column()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger conversations_updated_at
  before update on conversations
  for each row execute function update_updated_at_column();
