"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Link2,
  RefreshCw,
  Unlink,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Mail,
  CreditCard,
  BookOpen,
  X,
  Eye,
  EyeOff,
} from "lucide-react";
import { useMergeLink } from "@mergeapi/react-merge-link";
import type { Integration, IntegrationProvider } from "@/types";
import {
  fetchIntegrations,
  createLinkToken,
  createIntegration,
  syncIntegration,
  deleteIntegration,
  connectFloat,
  getGmailAuthUrl,
} from "@/lib/api";

// ── Integration catalog definitions ──────────────────────────

interface IntegrationDef {
  slug: IntegrationProvider;
  name: string;
  description: string;
  category: "accounting" | "email" | "spend";
  icon: React.ReactNode;
  mergeSlug?: string; // for Merge.dev single-integration mode
}

const INTEGRATION_CATALOG: IntegrationDef[] = [
  {
    slug: "quickbooks",
    name: "QuickBooks Online",
    description: "Sync accounts, balances, and transactions from QBO.",
    category: "accounting",
    icon: <BookOpen size={22} className="text-green-500" />,
    mergeSlug: "quickbooks-online",
  },
  {
    slug: "netsuite",
    name: "NetSuite",
    description: "Import GL accounts and transactions from Oracle NetSuite.",
    category: "accounting",
    icon: <BookOpen size={22} className="text-blue-500" />,
    mergeSlug: "netsuite",
  },
  {
    slug: "gmail",
    name: "Gmail",
    description: "Connect your inbox to surface invoices and receipts.",
    category: "email",
    icon: <Mail size={22} className="text-red-500" />,
  },
  {
    slug: "float",
    name: "Float",
    description: "Import card and account transactions from Float Financial.",
    category: "spend",
    icon: <CreditCard size={22} className="text-violet-500" />,
  },
];

const CATEGORY_LABELS: Record<string, string> = {
  accounting: "Accounting",
  email: "Email",
  spend: "Spend Management",
};

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
  const match = INTEGRATION_CATALOG.find((d) => d.slug === provider);
  return match?.name ?? provider;
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

// ── Float API Key Dialog ─────────────────────────────────────

function FloatKeyDialog({
  open,
  onClose,
  onSubmit,
  submitting,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (key: string) => void;
  submitting: boolean;
}) {
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setKey("");
      setShowKey(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Connect Float
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
          >
            <X size={18} />
          </button>
        </div>
        <p className="text-sm text-zinc-500 mb-4">
          Enter your Float API token. You can generate one from the Float
          dashboard under Settings &rarr; API.
        </p>
        <div className="relative mb-4">
          <input
            ref={inputRef}
            type={showKey ? "text" : "password"}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="float_api_XXXXXXXXXX"
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 pr-10 text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
          >
            {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={submitting}
            className="rounded-lg px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={() => onSubmit(key)}
            disabled={submitting || !key.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-violet-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Validating...
              </>
            ) : (
              "Connect"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page Component ───────────────────────────────────────────

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());

  // Merge Link state
  const [linkToken, setLinkToken] = useState<string | undefined>(undefined);
  const [pendingMergeProvider, setPendingMergeProvider] = useState<IntegrationDef | null>(null);
  const [connectingSlug, setConnectingSlug] = useState<string | null>(null);

  // Float dialog
  const [floatDialogOpen, setFloatDialogOpen] = useState(false);
  const [floatSubmitting, setFloatSubmitting] = useState(false);

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

  // Handle ?gmail=connected query param
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      setSyncResult("Gmail connected successfully!");
      loadIntegrations();
      window.history.replaceState({}, "", window.location.pathname);
    }
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
      if (!pendingMergeProvider) return;
      setError(null);
      try {
        const integration = await createIntegration(
          publicToken,
          pendingMergeProvider.slug,
          pendingMergeProvider.name
        );
        setIntegrations((prev) => [integration, ...prev]);

        if (integration.id) {
          setSyncingIds((prev) => new Set(prev).add(integration.id));
          try {
            await syncIntegration(integration.id);
            setSyncResult(`${pendingMergeProvider.name} connected and synced!`);
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
        setConnectingSlug(null);
        setLinkToken(undefined);
        setPendingMergeProvider(null);
      }
    },
    [pendingMergeProvider, loadIntegrations]
  );

  const { open: openMergeLink, isReady: isMergeLinkReady } = useMergeLink({
    linkToken,
    onSuccess: onMergeLinkSuccess,
    onExit: () => {
      setConnectingSlug(null);
      setLinkToken(undefined);
      setPendingMergeProvider(null);
    },
  });

  useEffect(() => {
    if (linkToken && isMergeLinkReady) {
      openMergeLink();
    }
  }, [linkToken, isMergeLinkReady, openMergeLink]);

  // ── Connect handlers ───────────────────────────────────────

  const handleConnectAccounting = useCallback(
    async (def: IntegrationDef) => {
      setConnectingSlug(def.slug);
      setError(null);
      setSyncResult(null);
      setPendingMergeProvider(def);
      try {
        const data = await createLinkToken(
          undefined,
          undefined,
          def.mergeSlug
        );
        setLinkToken(data.link_token);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to start integration flow"
        );
        setConnectingSlug(null);
        setPendingMergeProvider(null);
      }
    },
    []
  );

  const handleConnectGmail = useCallback(async () => {
    setConnectingSlug("gmail");
    setError(null);
    setSyncResult(null);
    try {
      const { auth_url } = await getGmailAuthUrl();
      window.location.href = auth_url;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start Gmail connection"
      );
      setConnectingSlug(null);
    }
  }, []);

  const handleConnectFloat = useCallback(
    async (apiKey: string) => {
      setFloatSubmitting(true);
      setError(null);
      setSyncResult(null);
      try {
        const integration = await connectFloat(apiKey);
        setIntegrations((prev) => [integration, ...prev]);
        setFloatDialogOpen(false);
        setSyncResult("Float connected successfully!");

        if (integration.id) {
          setSyncingIds((prev) => new Set(prev).add(integration.id));
          try {
            await syncIntegration(integration.id);
            setSyncResult("Float connected and synced!");
          } catch {
            // initial sync failure is non-fatal
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
          err instanceof Error ? err.message : "Failed to connect Float"
        );
      } finally {
        setFloatSubmitting(false);
        setConnectingSlug(null);
      }
    },
    [loadIntegrations]
  );

  const handleConnect = useCallback(
    (def: IntegrationDef) => {
      if (def.mergeSlug) {
        handleConnectAccounting(def);
      } else if (def.slug === "gmail") {
        handleConnectGmail();
      } else if (def.slug === "float") {
        setConnectingSlug("float");
        setFloatDialogOpen(true);
      }
    },
    [handleConnectAccounting, handleConnectGmail]
  );

  // ── Sync / disconnect ─────────────────────────────────────

  const handleSync = useCallback(
    async (id: string) => {
      setSyncingIds((prev) => new Set(prev).add(id));
      setError(null);
      setSyncResult(null);
      try {
        await syncIntegration(id);
        setSyncResult("Sync started.");
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

  // ── Derived data ───────────────────────────────────────────

  const connectedProviders = new Set(integrations.map((i) => i.provider));
  const categories = ["accounting", "email", "spend"] as const;

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
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-2xl space-y-6">
          {/* Banners */}
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

          {/* Connected integrations */}
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex items-center gap-2 text-zinc-500">
                <Loader2 size={20} className="animate-spin" />
                <span className="text-sm">Loading integrations...</span>
              </div>
            </div>
          ) : (
            <>
              {integrations.length > 0 && (
                <div>
                  <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                    Connected ({integrations.length})
                  </h2>
                  <div className="space-y-2">
                    {integrations.map((integration) => {
                      const isSyncing =
                        integration.status === "syncing" ||
                        syncingIds.has(integration.id);
                      const catalogDef = INTEGRATION_CATALOG.find(
                        (d) => d.slug === integration.provider
                      );

                      return (
                        <div
                          key={integration.id}
                          className="flex items-center gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 px-4 py-3 transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50"
                        >
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800">
                            {catalogDef?.icon ?? (
                              <Link2 size={20} className="text-orange-400" />
                            )}
                          </div>

                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-200">
                              {integration.integration_name ||
                                providerLabel(integration.provider)}
                            </p>
                            <div className="flex items-center gap-2 text-xs text-zinc-500">
                              <span>
                                {providerLabel(integration.provider)}
                              </span>
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

                          <StatusBadge
                            status={
                              isSyncing ? "syncing" : integration.status
                            }
                          />

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
                              title="Disconnect"
                            >
                              <Unlink size={16} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Available integrations catalog */}
              <div className="space-y-6">
                {categories.map((cat) => {
                  const defs = INTEGRATION_CATALOG.filter(
                    (d) => d.category === cat
                  );
                  return (
                    <div key={cat}>
                      <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                        {CATEGORY_LABELS[cat]}
                      </h2>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {defs.map((def) => {
                          const isConnected = connectedProviders.has(def.slug);
                          const isConnecting = connectingSlug === def.slug;

                          return (
                            <div
                              key={def.slug}
                              className="flex flex-col justify-between rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 p-4 transition-colors hover:border-zinc-300 dark:hover:border-zinc-700"
                            >
                              <div className="flex items-start gap-3 mb-3">
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800">
                                  {def.icon}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                                    {def.name}
                                  </p>
                                  <p className="text-xs text-zinc-500 mt-0.5">
                                    {def.description}
                                  </p>
                                </div>
                              </div>
                              <button
                                onClick={() => handleConnect(def)}
                                disabled={isConnected || isConnecting}
                                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm font-medium text-zinc-700 dark:text-zinc-300 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                {isConnected ? (
                                  <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                                    <CheckCircle2 size={14} />
                                    Connected
                                  </span>
                                ) : isConnecting ? (
                                  <span className="inline-flex items-center gap-1">
                                    <Loader2
                                      size={14}
                                      className="animate-spin"
                                    />
                                    Connecting...
                                  </span>
                                ) : (
                                  "Connect"
                                )}
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Float API key dialog */}
      <FloatKeyDialog
        open={floatDialogOpen}
        onClose={() => {
          setFloatDialogOpen(false);
          setConnectingSlug(null);
        }}
        onSubmit={handleConnectFloat}
        submitting={floatSubmitting}
      />
    </div>
  );
}
