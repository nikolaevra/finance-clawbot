-- ============================================================
-- Automation Audit Log: durable event log for app activity
-- ============================================================

create table if not exists automation_audit_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  conversation_id uuid references conversations(id) on delete set null,
  workflow_run_id uuid references workflow_runs(id) on delete set null,
  event_type text not null,
  event_category text not null,
  event_source text not null,
  status text,
  actor text,
  title text not null,
  message text,
  detail text,
  details jsonb not null default '{}'::jsonb,
  tool_name text,
  step_id text,
  workflow_name text,
  external_service text,
  external_endpoint text,
  request_id text,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists idx_audit_log_user_occurred_at
  on automation_audit_log (user_id, occurred_at desc);

create index if not exists idx_audit_log_user_category_occurred_at
  on automation_audit_log (user_id, event_category, occurred_at desc);

create index if not exists idx_audit_log_user_type_occurred_at
  on automation_audit_log (user_id, event_type, occurred_at desc);

create index if not exists idx_audit_log_user_source_occurred_at
  on automation_audit_log (user_id, event_source, occurred_at desc);

alter table automation_audit_log enable row level security;

create policy "Users can read own audit log"
  on automation_audit_log for select using (auth.uid() = user_id);

create policy "Service role can insert audit log"
  on automation_audit_log for insert with check (true);
