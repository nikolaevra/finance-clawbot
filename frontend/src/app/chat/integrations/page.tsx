"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Link2,
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
  deleteIntegration,
  connectFloat,
  getGmailAuthUrl,
} from "@/lib/api";

interface IntegrationDef {
  slug: IntegrationProvider;
  name: string;
  description: string;
  category: "accounting" | "email" | "spend";
  icon: React.ReactNode;
  mergeSlug?: string;
}

const INTEGRATION_CATALOG: IntegrationDef[] = [
  {
    slug: "quickbooks",
    name: "QuickBooks Online",
    description: "Connect accounts and transactions from QBO.",
    category: "accounting",
    icon: <BookOpen size={20} className="text-emerald-400/70" strokeWidth={1.5} />,
    mergeSlug: "quickbooks-online",
  },
  {
    slug: "netsuite",
    name: "NetSuite",
    description: "Connect GL accounts and transactions from Oracle NetSuite.",
    category: "accounting",
    icon: <BookOpen size={20} className="text-blue-400/70" strokeWidth={1.5} />,
    mergeSlug: "netsuite",
  },
  {
    slug: "gmail",
    name: "Gmail",
    description: "Connect your inbox to surface invoices and receipts.",
    category: "email",
    icon: <Mail size={20} className="text-red-400/70" strokeWidth={1.5} />,
  },
  {
    slug: "float",
    name: "Float",
    description: "Connect card and account transactions from Float Financial.",
    category: "spend",
    icon: <CreditCard size={20} className="text-blue-400/70" strokeWidth={1.5} />,
  },
];

const CATEGORY_LABELS: Record<string, string> = {
  accounting: "Accounting",
  email: "Email",
  spend: "Spend Management",
};

export function timeAgo(dateStr: string | null): string {
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

export function providerLabel(provider: string): string {
  const match = INTEGRATION_CATALOG.find((d) => d.slug === provider);
  return match?.name ?? provider;
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "active":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400/80">
          <CheckCircle2 size={9} />
          Active
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-400/10 px-2 py-0.5 text-[10px] font-medium text-red-400/80">
          <AlertCircle size={9} />
          Error
        </span>
      );
    default:
      return null;
  }
}

function FloatKeyDialog({
  onClose,
  onSubmit,
  submitting,
}: {
  onClose: () => void;
  onSubmit: (key: string) => void;
  submitting: boolean;
}) {
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 100);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-3xl bg-card ring-1 ring-foreground/[0.08] p-7 shadow-2xl shadow-black/40">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-foreground">
            Connect Float
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-foreground/25 hover:text-foreground/50 hover:bg-foreground/[0.06]"
          >
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
        <p className="text-sm text-foreground/60 mb-5">
          Enter your Float API token. You can generate one from the Float
          dashboard under Settings &rarr; API.
        </p>
        <div className="relative mb-5">
          <input
            ref={inputRef}
            type={showKey ? "text" : "password"}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="float_api_XXXXXXXXXX"
            className="w-full rounded-xl bg-foreground/[0.06] ring-1 ring-foreground/[0.08] px-4 py-2.5 pr-10 text-sm text-foreground placeholder:text-foreground/35 focus:outline-none focus:ring-foreground/[0.2]"
          />
          <button
            type="button"
            onClick={() => setShowKey((prev) => !prev)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-foreground/25 hover:text-foreground/50"
          >
            {showKey ? <EyeOff size={14} strokeWidth={1.5} /> : <Eye size={14} strokeWidth={1.5} />}
          </button>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={submitting}
            className="rounded-xl px-4 py-2 text-sm text-foreground/60 hover:text-foreground hover:bg-foreground/[0.06]"
          >
            Cancel
          </button>
          <button
            onClick={() => onSubmit(key)}
            disabled={submitting || !key.trim()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-blue-500 px-5 py-2 text-sm font-medium text-white hover:bg-blue-400 shadow-sm shadow-blue-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <>
                <Loader2 size={13} className="animate-spin" />
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

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [linkToken, setLinkToken] = useState<string | undefined>(undefined);
  const [pendingMergeProvider, setPendingMergeProvider] = useState<IntegrationDef | null>(null);
  const [connectingSlug, setConnectingSlug] = useState<string | null>(null);

  const [floatDialogOpen, setFloatDialogOpen] = useState(false);
  const [floatSubmitting, setFloatSubmitting] = useState(false);

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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      setSuccessMsg("Gmail connected successfully!");
      loadIntegrations();
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [loadIntegrations]);

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
        setSuccessMsg(`${pendingMergeProvider.name} connected!`);
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
    [pendingMergeProvider]
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

  const handleConnectAccounting = useCallback(
    async (def: IntegrationDef) => {
      setConnectingSlug(def.slug);
      setError(null);
      setSuccessMsg(null);
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
    setSuccessMsg(null);
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
      setSuccessMsg(null);
      try {
        const integration = await connectFloat(apiKey);
        setIntegrations((prev) => [integration, ...prev]);
        setFloatDialogOpen(false);
        setSuccessMsg("Float connected successfully!");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to connect Float"
        );
      } finally {
        setFloatSubmitting(false);
        setConnectingSlug(null);
      }
    },
    []
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

  const handleDisconnect = useCallback(
    async (id: string, name: string) => {
      if (
        !confirm(
          `Disconnect "${name}"? This cannot be undone.`
        )
      )
        return;
      try {
        await deleteIntegration(id);
        setIntegrations((prev) => prev.filter((i) => i.id !== id));
        setSuccessMsg(null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to disconnect"
        );
      }
    },
    []
  );

  const connectedProviders = new Set(integrations.map((i) => i.provider));
  const categories = ["accounting", "email", "spend"] as const;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-5">
        <Link2 size={18} className="text-blue-400" strokeWidth={1.5} />
        <h1 className="text-lg font-semibold text-foreground tracking-tight">
          Integrations
        </h1>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-2">
        <div className="mx-auto max-w-2xl space-y-6">
          {error && (
            <div className="flex items-center gap-2 rounded-2xl bg-red-400/[0.06] ring-1 ring-red-400/10 px-4 py-3">
              <AlertCircle size={14} className="shrink-0 text-red-400/70" strokeWidth={1.5} />
              <p className="text-sm text-red-400/80">{error}</p>
              <button
                onClick={() => setError(null)}
                className="ml-auto text-xs text-red-400/40 hover:text-red-400/60"
              >
                Dismiss
              </button>
            </div>
          )}

          {successMsg && (
            <div className="flex items-center gap-2 rounded-2xl bg-emerald-400/[0.06] ring-1 ring-emerald-400/10 px-4 py-3">
              <CheckCircle2 size={14} className="shrink-0 text-emerald-400/70" strokeWidth={1.5} />
              <p className="text-sm text-emerald-400/80">
                {successMsg}
              </p>
              <button
                onClick={() => setSuccessMsg(null)}
                className="ml-auto text-xs text-emerald-400/40 hover:text-emerald-400/60"
              >
                Dismiss
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={20} className="animate-spin text-foreground/20" />
            </div>
          ) : (
            <>
              {integrations.length > 0 && (
                <div>
                  <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-foreground/50">
                    Connected ({integrations.length})
                  </h2>
                  <div className="space-y-1.5">
                    {integrations.map((integration) => {
                      const catalogDef = INTEGRATION_CATALOG.find(
                        (d) => d.slug === integration.provider
                      );

                      return (
                        <div
                          key={integration.id}
                          className="flex items-center gap-3 rounded-2xl bg-background ring-1 ring-foreground/[0.08] shadow-sm shadow-black/5 px-4 py-3.5 transition-all hover:shadow-md hover:shadow-black/8"
                        >
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06]">
                            {catalogDef?.icon ?? (
                              <Link2 size={18} className="text-foreground/50" strokeWidth={1.5} />
                            )}
                          </div>

                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-foreground">
                              {integration.integration_name ||
                                providerLabel(integration.provider)}
                            </p>
                            <div className="flex items-center gap-2 text-xs text-foreground/50">
                              <span>
                                {providerLabel(integration.provider)}
                              </span>
                              <span className="text-foreground/20">/</span>
                              <span className="inline-flex items-center gap-1">
                                <Clock size={10} strokeWidth={1.5} />
                                Connected {timeAgo(integration.created_at)}
                              </span>
                            </div>
                          </div>

                          <StatusBadge status={integration.status} />

                          <button
                            onClick={() =>
                              handleDisconnect(
                                integration.id,
                                integration.integration_name ||
                                  providerLabel(integration.provider)
                              )
                            }
                            className="shrink-0 rounded-lg p-2 text-foreground/35 hover:text-red-400 hover:bg-red-400/10"
                            title="Disconnect"
                          >
                            <Unlink size={14} strokeWidth={1.5} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="space-y-8">
                {categories.map((cat) => {
                  const defs = INTEGRATION_CATALOG.filter(
                    (d) => d.category === cat
                  );
                  return (
                    <div key={cat}>
                      <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-foreground/50">
                        {CATEGORY_LABELS[cat]}
                      </h2>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {defs.map((def) => {
                          const isConnected = connectedProviders.has(def.slug);
                          const isConnecting = connectingSlug === def.slug;

                          return (
                            <div
                              key={def.slug}
                              className="flex flex-col justify-between rounded-2xl bg-background ring-1 ring-foreground/[0.08] shadow-sm shadow-black/5 p-5 transition-all hover:shadow-md hover:shadow-black/8"
                            >
                              <div className="flex items-start gap-3 mb-4">
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06]">
                                  {def.icon}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-medium text-foreground">
                                    {def.name}
                                  </p>
                                  <p className="text-xs text-foreground/60 mt-0.5">
                                    {def.description}
                                  </p>
                                </div>
                              </div>
                              <button
                                onClick={() => handleConnect(def)}
                                disabled={isConnected || isConnecting}
                                className="w-full rounded-xl ring-1 ring-foreground/[0.08] px-3 py-2 text-sm font-medium text-foreground/70 hover:text-foreground hover:bg-foreground/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {isConnected ? (
                                  <span className="inline-flex items-center gap-1 text-emerald-400/80">
                                    <CheckCircle2 size={13} />
                                    Connected
                                  </span>
                                ) : isConnecting ? (
                                  <span className="inline-flex items-center gap-1">
                                    <Loader2
                                      size={13}
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

      {floatDialogOpen && (
        <FloatKeyDialog
          onClose={() => {
            setFloatDialogOpen(false);
            setConnectingSlug(null);
          }}
          onSubmit={handleConnectFloat}
          submitting={floatSubmitting}
        />
      )}
    </div>
  );
}
