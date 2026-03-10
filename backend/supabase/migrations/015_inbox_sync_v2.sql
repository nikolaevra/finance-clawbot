-- ============================================================
-- 015 - Inbox sync v2 tables
-- ============================================================

-- ── email_threads ────────────────────────────────────────────
create table if not exists public.email_threads (
    id                          uuid primary key default gen_random_uuid(),
    user_id                     uuid not null references auth.users(id) on delete cascade,
    integration_id              uuid not null references public.integrations(id) on delete cascade,
    gmail_thread_id             text not null,
    subject_normalized          text not null default '',
    participants_json           jsonb not null default '[]'::jsonb,
    last_message_internal_at    timestamptz,
    has_unread                  boolean not null default false,
    snippet                     text not null default '',
    history_id_high_watermark   text,
    created_at                  timestamptz not null default now(),
    updated_at                  timestamptz not null default now(),

    constraint email_threads_integration_thread_unique unique (integration_id, gmail_thread_id)
);

create index if not exists idx_email_threads_user_last_message
    on public.email_threads (user_id, last_message_internal_at desc);
create index if not exists idx_email_threads_integration_thread
    on public.email_threads (integration_id, gmail_thread_id);

alter table public.email_threads enable row level security;

drop policy if exists "Users can read own email threads" on public.email_threads;
create policy "Users can read own email threads"
    on public.email_threads for select using (auth.uid() = user_id);

drop policy if exists "Service role full access on email_threads" on public.email_threads;
create policy "Service role full access on email_threads"
    on public.email_threads for all using (
        (current_setting('request.jwt.claims', true)::json ->> 'role') = 'service_role'
    );

-- ── emails ───────────────────────────────────────────────────
create table if not exists public.emails (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 uuid not null references auth.users(id) on delete cascade,
    integration_id          uuid not null references public.integrations(id) on delete cascade,
    gmail_message_id        text not null,
    gmail_thread_id         text not null,
    internal_date_ts        bigint,
    from_json               jsonb not null default '{}'::jsonb,
    to_json                 jsonb not null default '[]'::jsonb,
    cc_json                 jsonb not null default '[]'::jsonb,
    bcc_json                jsonb not null default '[]'::jsonb,
    subject                 text not null default '',
    snippet                 text not null default '',
    body_text               text not null default '',
    body_html_sanitized     text not null default '',
    payload_json            jsonb not null default '{}'::jsonb,
    label_ids_json          jsonb not null default '[]'::jsonb,
    is_read                 boolean not null default true,
    is_starred              boolean not null default false,
    is_draft                boolean not null default false,
    is_sent                 boolean not null default false,
    has_attachments         boolean not null default false,
    message_id_header       text not null default '',
    in_reply_to_header      text not null default '',
    references_header       text not null default '',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    deleted_at              timestamptz,

    constraint emails_integration_message_unique unique (integration_id, gmail_message_id)
);

create index if not exists idx_emails_user_internal_date
    on public.emails (user_id, internal_date_ts desc);
create index if not exists idx_emails_integration_thread
    on public.emails (integration_id, gmail_thread_id);
create index if not exists idx_emails_active_by_integration
    on public.emails (integration_id, created_at desc)
    where deleted_at is null;

alter table public.emails enable row level security;

drop policy if exists "Users can read own emails" on public.emails;
create policy "Users can read own emails"
    on public.emails for select using (auth.uid() = user_id and deleted_at is null);

drop policy if exists "Service role full access on emails" on public.emails;
create policy "Service role full access on emails"
    on public.emails for all using (
        (current_setting('request.jwt.claims', true)::json ->> 'role') = 'service_role'
    );

-- ── email_attachments ────────────────────────────────────────
create table if not exists public.email_attachments (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 uuid not null references auth.users(id) on delete cascade,
    integration_id          uuid not null references public.integrations(id) on delete cascade,
    email_id                uuid not null references public.emails(id) on delete cascade,
    gmail_message_id        text not null,
    gmail_attachment_id     text not null,
    filename                text not null default '',
    mime_type               text not null default '',
    size_bytes              bigint not null default 0,
    storage_key             text,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),

    constraint email_attachments_unique unique (
        integration_id, gmail_message_id, gmail_attachment_id
    )
);

create index if not exists idx_email_attachments_email
    on public.email_attachments (email_id);

alter table public.email_attachments enable row level security;

drop policy if exists "Users can read own email attachments" on public.email_attachments;
create policy "Users can read own email attachments"
    on public.email_attachments for select using (auth.uid() = user_id);

drop policy if exists "Service role full access on email_attachments" on public.email_attachments;
create policy "Service role full access on email_attachments"
    on public.email_attachments for all using (
        (current_setting('request.jwt.claims', true)::json ->> 'role') = 'service_role'
    );

-- ── gmail_sync_state ─────────────────────────────────────────
create table if not exists public.gmail_sync_state (
    id                  uuid primary key default gen_random_uuid(),
    user_id             uuid not null references auth.users(id) on delete cascade,
    integration_id      uuid not null references public.integrations(id) on delete cascade,
    last_history_id     text,
    last_full_sync_at   timestamptz,
    last_delta_sync_at  timestamptz,
    sync_cursor_status  text not null default 'idle',
    last_error          text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),

    constraint gmail_sync_state_integration_unique unique (integration_id)
);

create index if not exists idx_gmail_sync_state_user
    on public.gmail_sync_state (user_id);

alter table public.gmail_sync_state enable row level security;

drop policy if exists "Users can read own gmail sync state" on public.gmail_sync_state;
create policy "Users can read own gmail sync state"
    on public.gmail_sync_state for select using (auth.uid() = user_id);

drop policy if exists "Service role full access on gmail_sync_state" on public.gmail_sync_state;
create policy "Service role full access on gmail_sync_state"
    on public.gmail_sync_state for all using (
        (current_setting('request.jwt.claims', true)::json ->> 'role') = 'service_role'
    );
