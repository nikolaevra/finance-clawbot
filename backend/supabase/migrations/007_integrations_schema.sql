-- ============================================================
-- 006  Accounting Integrations (Merge.dev)
-- ============================================================
-- Three tables:
--   1. integrations          – connected accounting platforms per user
--   2. accounting_accounts   – normalised chart-of-accounts
--   3. accounting_transactions – normalised transactions / journal entries
-- ============================================================

-- ── 1. integrations ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS integrations (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider        text NOT NULL DEFAULT 'quickbooks',       -- e.g. quickbooks, xero, netsuite
    integration_name text NOT NULL DEFAULT 'QuickBooks Online',
    account_token   text NOT NULL,                            -- Merge.dev account token
    status          text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','syncing','error','disconnected')),
    last_sync_at    timestamptz,
    last_sync_status text,
    merge_account_id text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_integrations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_integrations_updated_at
    BEFORE UPDATE ON integrations
    FOR EACH ROW
    EXECUTE FUNCTION update_integrations_updated_at();

-- RLS
ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own integrations"
    ON integrations FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own integrations"
    ON integrations FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own integrations"
    ON integrations FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own integrations"
    ON integrations FOR DELETE
    USING (auth.uid() = user_id);

-- Service role bypass (backend uses service role key)
CREATE POLICY "Service role full access on integrations"
    ON integrations FOR ALL
    USING (auth.role() = 'service_role');

-- Index
CREATE INDEX idx_integrations_user_id ON integrations (user_id);


-- ── 2. accounting_accounts ──────────────────────────────────

CREATE TABLE IF NOT EXISTS accounting_accounts (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_id          uuid NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    remote_id               text NOT NULL,
    name                    text NOT NULL,
    description             text,
    classification          text,          -- asset, liability, equity, revenue, expense
    type                    text,          -- e.g. bank, accounts_receivable, other_current_asset …
    status                  text,          -- active, archived
    current_balance         numeric,
    currency                text NOT NULL DEFAULT 'USD',
    parent_account_remote_id text,
    company                 text,
    remote_created_at       timestamptz,
    remote_updated_at       timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

-- Upsert key – one row per remote account per integration
ALTER TABLE accounting_accounts
    ADD CONSTRAINT uq_accounting_accounts_integration_remote
    UNIQUE (integration_id, remote_id);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_accounting_accounts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_accounting_accounts_updated_at
    BEFORE UPDATE ON accounting_accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_accounting_accounts_updated_at();

-- RLS
ALTER TABLE accounting_accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own accounting_accounts"
    ON accounting_accounts FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on accounting_accounts"
    ON accounting_accounts FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_acct_accounts_user ON accounting_accounts (user_id);
CREATE INDEX idx_acct_accounts_integration ON accounting_accounts (integration_id);


-- ── 3. accounting_transactions ──────────────────────────────

CREATE TABLE IF NOT EXISTS accounting_transactions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_id      uuid NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    remote_id           text NOT NULL,
    transaction_date    date,
    number              text,              -- cheque / invoice number
    memo                text,
    total_amount        numeric,
    currency            text NOT NULL DEFAULT 'USD',
    contact_name        text,              -- vendor / customer
    account_name        text,              -- primary account (denormalised)
    account_remote_id   text,              -- FK-ish ref to accounting_accounts.remote_id
    transaction_type    text,              -- expense, income, journal_entry, etc.
    line_items          jsonb,             -- [{account, amount, description, …}]
    remote_created_at   timestamptz,
    remote_updated_at   timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Upsert key – one row per remote transaction per integration
ALTER TABLE accounting_transactions
    ADD CONSTRAINT uq_accounting_transactions_integration_remote
    UNIQUE (integration_id, remote_id);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_accounting_transactions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_accounting_transactions_updated_at
    BEFORE UPDATE ON accounting_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_accounting_transactions_updated_at();

-- RLS
ALTER TABLE accounting_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own accounting_transactions"
    ON accounting_transactions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on accounting_transactions"
    ON accounting_transactions FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_acct_txns_user_date
    ON accounting_transactions (user_id, transaction_date DESC);
CREATE INDEX idx_acct_txns_integration
    ON accounting_transactions (integration_id);
CREATE INDEX idx_acct_txns_amount
    ON accounting_transactions (user_id, total_amount);
