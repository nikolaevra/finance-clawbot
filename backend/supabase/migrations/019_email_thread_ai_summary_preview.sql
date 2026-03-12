-- ============================================================
-- 019 - Email thread AI summary preview
-- ============================================================

alter table public.email_threads
    add column if not exists ai_summary_preview text not null default '',
    add column if not exists ai_summary_updated_at timestamptz;

create index if not exists idx_email_threads_user_summary_updated
    on public.email_threads (user_id, ai_summary_updated_at desc nulls last);
