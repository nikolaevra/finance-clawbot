-- ============================================================
-- 010 – Gmail (emails) and Float (float_transactions) tables
-- ============================================================

-- ── emails ────────────────────────────────────────────────────

create table if not exists public.emails (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null references auth.users(id) on delete cascade,
    integration_id uuid not null references public.integrations(id) on delete cascade,
    remote_id      text not null,
    thread_id      text,
    subject        text not null default '',
    from_address   text not null default '',
    to_addresses   text not null default '',
    date           text not null default '',
    snippet        text not null default '',
    body_text      text not null default '',
    labels         jsonb default '[]'::jsonb,
    created_at     timestamptz not null default now(),

    constraint emails_integration_remote_unique unique (integration_id, remote_id)
);

create index if not exists idx_emails_user_id on public.emails (user_id);
create index if not exists idx_emails_integration_id on public.emails (integration_id);

alter table public.emails enable row level security;

create policy "Users can read own emails"
    on public.emails for select using (auth.uid() = user_id);

create policy "Service role full access on emails"
    on public.emails for all using (
        (current_setting('request.jwt.claims', true)::json ->> 'role') = 'service_role'
    );


-- ── float_transactions ────────────────────────────────────────

create table if not exists public.float_transactions (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null references auth.users(id) on delete cascade,
    integration_id       uuid not null references public.integrations(id) on delete cascade,
    remote_id            text not null,
    source               text not null default 'card',   -- 'card' or 'account'
    transaction_type     text,
    description          text,
    amount_cents         bigint,
    currency             text not null default 'CAD',
    spender_email        text,
    team_name            text,
    vendor_name          text,
    gl_code_external_id  text,
    account_id           text,
    account_type         text,
    remote_created_at    timestamptz,
    remote_updated_at    timestamptz,
    created_at           timestamptz not null default now(),

    constraint float_txn_integration_remote_unique unique (integration_id, remote_id)
);

create index if not exists idx_float_txn_user_id on public.float_transactions (user_id);
create index if not exists idx_float_txn_integration_id on public.float_transactions (integration_id);
create index if not exists idx_float_txn_user_date on public.float_transactions (user_id, remote_created_at desc);

alter table public.float_transactions enable row level security;

create policy "Users can read own float transactions"
    on public.float_transactions for select using (auth.uid() = user_id);

create policy "Service role full access on float_transactions"
    on public.float_transactions for all using (
        (current_setting('request.jwt.claims', true)::json ->> 'role') = 'service_role'
    );
