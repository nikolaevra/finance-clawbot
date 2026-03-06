-- ============================================================
-- 011 – Drop synced-data tables
-- ============================================================
-- The app no longer stores integration data locally. All data
-- (accounts, transactions, emails) is queried live from external
-- APIs via AI tools. Only the `integrations` table remains to
-- track connection metadata and credentials.
-- ============================================================

-- Drop tables (order matters due to FK constraints)
DROP TABLE IF EXISTS public.accounting_transactions CASCADE;
DROP TABLE IF EXISTS public.accounting_accounts CASCADE;
DROP TABLE IF EXISTS public.float_transactions CASCADE;
DROP TABLE IF EXISTS public.emails CASCADE;

-- Clean up orphaned trigger functions from 006
DROP FUNCTION IF EXISTS update_accounting_accounts_updated_at() CASCADE;
DROP FUNCTION IF EXISTS update_accounting_transactions_updated_at() CASCADE;
