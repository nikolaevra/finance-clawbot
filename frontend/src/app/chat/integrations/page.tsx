"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Link2,
  Plus,
  RefreshCw,
  Unlink,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
} from "lucide-react";
import { useMergeLink } from "@mergeapi/react-merge-link";
import type { Integration } from "@/types";
import {
  fetchIntegrations,
  createLinkToken,
  createIntegration,
  syncIntegration,
  deleteIntegration,
} from "@/lib/api";

// ── Helpers ──────────────────────────────────────────────────

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function providerLabel(provider: string): string {
  switch (provider) {
    case "quickbooks":
      return "QuickBooks Online";
    case "xero":
      return "Xero";
    case "netsuite":
      return "NetSuite";
    default:
      return provider;
  }
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "active":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 size={10} />
          Active
        </span>
      );
    case "syncing":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-[11px] font-medium text-blue-600 dark:text-blue-400">
          <Loader2 size={10} className="animate-spin" />
          Syncing
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-600 dark:text-red-400">
          <AlertCircle size={10} />
          Error
        </span>
      );
    default:
      return null;
  }
}

// ── Page Component ───────────────────────────────────────────

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [linkToken, setLinkToken] = useState<string | undefined>(undefined);
  const [connecting, setConnecting] = useState(false);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [syncResult, setSyncResult] = useState<string | null>(null);

  // ── Load integrations ──────────────────────────────────────

  const loadIntegrations = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchIntegrations();
      setIntegrations(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load integrations"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  // Poll while any integration is syncing
  useEffect(() => {
    const hasSyncing = integrations.some((i) => i.status === "syncing");
    if (!hasSyncing) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchIntegrations();
        setIntegrations(data);
        if (!data.some((i) => i.status === "syncing")) {
          clearInterval(interval);
        }
      } catch {
        // silent
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [integrations]);

  // ── Merge Link hook ────────────────────────────────────────

  const onMergeLinkSuccess = useCallback(
    async (publicToken: string) => {
      setConnecting(true);
      setError(null);
      try {
        const integration = await createIntegration(publicToken);
        setIntegrations((prev) => [integration, ...prev]);

        // Trigger initial sync
        if (integration.id) {
          setSyncingIds((prev) => new Set(prev).add(integration.id));
          try {
            const result = await syncIntegration(integration.id);
            setSyncResult(
              `Initial sync complete: ${result.accounts_synced} accounts, ${result.transactions_synced} transactions imported.`
            );
          } catch (err) {
            setError(
              err instanceof Error ? err.message : "Initial sync failed"
            );
          } finally {
            setSyncingIds((prev) => {
              const next = new Set(prev);
              next.delete(integration.id);
              return next;
            });
          }
          await loadIntegrations();
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to create integration"
        );
      } finally {
        setConnecting(false);
        setLinkToken(undefined);
      }
    },
    [loadIntegrations]
  );

  const { open: openMergeLink, isReady: isMergeLinkReady } = useMergeLink({
    linkToken,
    onSuccess: onMergeLinkSuccess,
    onExit: () => {
      setConnecting(false);
      setLinkToken(undefined);
    },
  });

  // Open Merge Link once token is ready
  useEffect(() => {
    if (linkToken && isMergeLinkReady) {
      openMergeLink();
    }
  }, [linkToken, isMergeLinkReady, openMergeLink]);

  // ── Handlers ───────────────────────────────────────────────

  const handleAddIntegration = useCallback(async () => {
    setConnecting(true);
    setError(null);
    setSyncResult(null);
    try {
      const data = await createLinkToken();
      setLinkToken(data.link_token);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start integration flow"
      );
      setConnecting(false);
    }
  }, []);

  const handleSync = useCallback(
    async (id: string) => {
      setSyncingIds((prev) => new Set(prev).add(id));
      setError(null);
      setSyncResult(null);
      try {
        const result = await syncIntegration(id);
        setSyncResult(
          `Sync complete: ${result.accounts_synced} accounts, ${result.transactions_synced} transactions imported.`
        );
        await loadIntegrations();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Sync failed");
      } finally {
        setSyncingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [loadIntegrations]
  );

  const handleDisconnect = useCallback(
    async (id: string, name: string) => {
      if (
        !confirm(
          `Disconnect "${name}"? This will remove all synced data and cannot be undone.`
        )
      )
        return;

      try {
        await deleteIntegration(id);
        setIntegrations((prev) => prev.filter((i) => i.id !== id));
        setSyncResult(null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to disconnect"
        );
      }
    },
    []
  );

  // ── Render ─────────────────────────────────────────────────

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="flex items-center gap-2">
          <Link2 size={20} className="text-orange-400" />
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Integrations
          </h1>
        </div>
        <button
          onClick={handleAddIntegration}
          disabled={connecting}
          className="inline-flex items-center gap-1.5 rounded-lg bg-orange-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {connecting ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Connecting...
            </>
          ) : (
            <>
              <Plus size={14} />
              Add Integration
            </>
          )}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-2xl space-y-6">
          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/10 px-4 py-3">
              <AlertCircle
                size={16}
                className="shrink-0 text-red-500 dark:text-red-400"
              />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
              <button
                onClick={() => setError(null)}
                className="ml-auto text-xs text-red-400/70 hover:text-red-500 dark:hover:text-red-400"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Sync success banner */}
          {syncResult && (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-900/10 px-4 py-3">
              <CheckCircle2
                size={16}
                className="shrink-0 text-emerald-500 dark:text-emerald-400"
              />
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                {syncResult}
              </p>
              <button
                onClick={() => setSyncResult(null)}
                className="ml-auto text-xs text-emerald-400/70 hover:text-emerald-500 dark:hover:text-emerald-400"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Integration list */}
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex items-center gap-2 text-zinc-500">
                <Loader2 size={20} className="animate-spin" />
                <span className="text-sm">Loading integrations...</span>
              </div>
            </div>
          ) : integrations.length > 0 ? (
            <div>
              <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                Connected Integrations ({integrations.length})
              </h2>
              <div className="space-y-2">
                {integrations.map((integration) => {
                  const isSyncing =
                    integration.status === "syncing" ||
                    syncingIds.has(integration.id);

                  return (
                    <div
                      key={integration.id}
                      className="flex items-center gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 px-4 py-3 transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50"
                    >
                      {/* Provider icon */}
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-orange-500/10">
                        <Link2 size={20} className="text-orange-400" />
                      </div>

                      {/* Info */}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-200">
                          {integration.integration_name ||
                            providerLabel(integration.provider)}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-zinc-500">
                          <span>{providerLabel(integration.provider)}</span>
                          <span>&middot;</span>
                          <span className="inline-flex items-center gap-1">
                            <Clock size={10} />
                            Synced {timeAgo(integration.last_sync_at)}
                          </span>
                          {integration.last_sync_status && (
                            <>
                              <span>&middot;</span>
                              <span className="truncate max-w-[200px]">
                                {integration.last_sync_status}
                              </span>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Status */}
                      <StatusBadge
                        status={isSyncing ? "syncing" : integration.status}
                      />

                      {/* Actions */}
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleSync(integration.id)}
                          disabled={isSyncing}
                          className="shrink-0 rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-blue-500 dark:hover:text-blue-400 disabled:opacity-40 disabled:cursor-not-allowed"
                          title="Sync data"
                        >
                          <RefreshCw
                            size={16}
                            className={isSyncing ? "animate-spin" : ""}
                          />
                        </button>
                        <button
                          onClick={() =>
                            handleDisconnect(
                              integration.id,
                              integration.integration_name ||
                                providerLabel(integration.provider)
                            )
                          }
                          disabled={isSyncing}
                          className="shrink-0 rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-red-500 dark:hover:text-red-400 disabled:opacity-40 disabled:cursor-not-allowed"
                          title="Disconnect integration"
                        >
                          <Unlink size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-zinc-200/50 dark:bg-zinc-800/50">
                <Link2
                  size={28}
                  className="text-zinc-400 dark:text-zinc-600"
                />
              </div>
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                No integrations connected
              </p>
              <p className="mt-1 max-w-xs text-xs text-zinc-500">
                Connect your accounting software (e.g. QuickBooks Online) to
                import accounts, balances, and transactions. The AI assistant
                will be able to answer questions about your financial data.
              </p>
              <button
                onClick={handleAddIntegration}
                disabled={connecting}
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {connecting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Connecting...
                  </>
                ) : (
                  <>
                    <Plus size={14} />
                    Add Integration
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
