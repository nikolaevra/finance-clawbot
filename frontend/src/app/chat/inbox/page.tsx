"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Archive,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Check,
  Download,
  FolderPlus,
  Forward,
  Inbox,
  Loader2,
  MailPlus,
  Paperclip,
  RefreshCw,
  Reply,
  Search,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import type { EmailAttachment, EmailMessage, EmailThread, InboxTab } from "@/types";
import {
  archiveInboxThread,
  createConversation,
  discardInboxThreadDrafts,
  downloadInboxAttachment,
  fetchInboxThread,
  fetchInboxThreads,
  forwardInboxEmail,
  markInboxMessageRead,
  replyInboxEmail,
  saveInboxAttachmentToDocuments,
  sendInboxDraft,
  sendInboxEmail,
} from "@/lib/api";
import { useSkills } from "@/lib/hooks/useSkills";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type ComposerMode = "new" | "reply" | "forward";
const THREAD_PAGE_SIZE = 75;
const MAX_THREADS_FOR_CONTEXT = 20;

const TABS: Array<{ id: InboxTab; label: string }> = [
  { id: "inbox", label: "Inbox" },
  { id: "all_mail", label: "All Mail" },
  { id: "skip_inbox", label: "Skip Inbox" },
  { id: "unread", label: "Unread" },
  { id: "sent", label: "Sent" },
  { id: "drafts", label: "Drafts" },
];

function formatTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function stripOuterHtmlShell(html: string): string {
  return html
    .replace(/<!doctype[^>]*>/gi, "")
    .replace(/<\/?(html|head|body)[^>]*>/gi, "");
}

function buildEmailHtmlDoc(subject: string, html: string): string {
  const safeSubject = escapeHtml(subject || "Email");
  const content = stripOuterHtmlShell(html || "");
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${safeSubject}</title>
    <style>
      :root { color-scheme: light; }
      html, body {
        margin: 0;
        padding: 0;
        background: #ffffff;
        color: #111827;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.45;
      }
      body {
        padding: 16px;
        overflow-wrap: anywhere;
      }
      #email-root {
        isolation: isolate;
      }
      #email-root img, #email-root video {
        max-width: 100%;
        height: auto;
      }
      #email-root table {
        max-width: 100%;
      }
      #email-root a {
        color: #2563eb;
      }
      #email-root blockquote {
        margin: 12px 0;
        padding-left: 12px;
        border-left: 3px solid #d1d5db;
      }
      #email-root pre, #email-root code {
        white-space: pre-wrap;
        word-break: break-word;
      }
    </style>
  </head>
  <body><div id="email-root">${content}</div></body>
</html>`;
}

function getSenderLabel(thread: EmailThread): string {
  const fallback = thread.participants_json?.[0];
  return (
    thread.latest_sender_name ||
    thread.latest_sender_email ||
    fallback?.name ||
    fallback?.email ||
    "Unknown sender"
  );
}

function mergeUniqueThreads(existing: EmailThread[], incoming: EmailThread[]): EmailThread[] {
  if (incoming.length === 0) return existing;
  const map = new Map(existing.map((thread) => [thread.gmail_thread_id, thread]));
  for (const thread of incoming) {
    map.set(thread.gmail_thread_id, thread);
  }
  return Array.from(map.values());
}

function getCollapsedMessagePreview(message: EmailMessage): string {
  const raw = message.body_text || message.snippet || "(No content)";
  return raw.replace(/\s+/g, " ").trim();
}

function buildSelectedThreadsContext(threads: EmailThread[]): string {
  const selected = threads.slice(0, MAX_THREADS_FOR_CONTEXT);
  const lines = selected.map((thread, index) => {
    const sender = getSenderLabel(thread);
    const subject = thread.subject_normalized || "(No subject)";
    const preview = thread.ai_summary_preview || thread.snippet || "(No preview)";
    const when = formatTime(thread.last_message_internal_at) || "Unknown time";
    return `${index + 1}. From: ${sender}; Subject: ${subject}; Last message: ${when}; Preview: ${preview}`;
  });

  const remaining = threads.length - selected.length;
  if (remaining > 0) {
    lines.push(`...and ${remaining} more selected threads not listed.`);
  }

  return [
    "Selected inbox thread context:",
    ...lines,
    "",
    "Use this context while answering the user's next request.",
  ].join("\n");
}

function InboxPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<InboxTab>("inbox");
  const [searchQuery, setSearchQuery] = useState("");
  const [threads, setThreads] = useState<EmailThread[]>([]);
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMoreThreads, setLoadingMoreThreads] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [hasMoreThreads, setHasMoreThreads] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [activeThreadPreview, setActiveThreadPreview] = useState<EmailThread | null>(null);
  const [loadingThreadDetail, setLoadingThreadDetail] = useState(false);
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [attachmentsByMessage, setAttachmentsByMessage] = useState<Record<string, EmailAttachment[]>>(
    {}
  );

  const [sending, setSending] = useState(false);
  const [sendingDraft, setSendingDraft] = useState(false);
  const [archivingThreadId, setArchivingThreadId] = useState<string | null>(null);
  const [attachmentActions, setAttachmentActions] = useState<Record<string, "downloading" | "saving" | "saved">>({});

  const [composerMode, setComposerMode] = useState<ComposerMode | null>(null);
  const [pendingComposerMode, setPendingComposerMode] = useState<ComposerMode | null>(null);
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeCc, setComposeCc] = useState("");
  const [expandedMessageIds, setExpandedMessageIds] = useState<Set<string>>(new Set());
  const [selectedThreadIds, setSelectedThreadIds] = useState<Set<string>>(new Set());
  const [bulkPrompt, setBulkPrompt] = useState("");
  const [selectedSkillName, setSelectedSkillName] = useState<string | null>(null);
  const [isBulkSending, setIsBulkSending] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const routeEmailId = searchParams.get("emailId");
  const loadContextRef = useRef(0);
  const loadingMoreRef = useRef(false);
  const listEndRef = useRef<HTMLDivElement | null>(null);
  const threadScrollRef = useRef<HTMLDivElement | null>(null);
  const lastMessageRef = useRef<HTMLElement | null>(null);
  const { skills, loading: skillsLoading } = useSkills();
  const enabledSkills = useMemo(() => skills.filter((skill) => skill.enabled), [skills]);

  const selectedThread = useMemo(() => {
    const fromList = threads.find((t) => t.gmail_thread_id === activeThreadId) || null;
    if (fromList) return fromList;
    if (activeThreadPreview?.gmail_thread_id === activeThreadId) return activeThreadPreview;
    return null;
  }, [threads, activeThreadId, activeThreadPreview]);

  const latestMessage = messages[messages.length - 1];
  const hasDraftMessages = useMemo(
    () => messages.some((message) => message.is_draft),
    [messages]
  );
  const selectedDraftMessage = useMemo(
    () =>
      [...messages]
        .reverse()
        .find(
          (message) =>
            message.is_draft || (message.label_ids_json || []).includes("DRAFT")
        ) || null,
    [messages]
  );

  const syncInboxUrl = useCallback(
    (emailId: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (emailId) {
        params.set("emailId", emailId);
      } else {
        params.delete("emailId");
      }
      const query = params.toString();
      const nextUrl = query ? `${pathname}?${query}` : pathname;
      router.push(nextUrl);
    },
    [pathname, router, searchParams]
  );

  const filteredThreads = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return threads;
    return threads.filter((thread) => {
      const sender = getSenderLabel(thread).toLowerCase();
      const senderEmail = (thread.latest_sender_email || "").toLowerCase();
      const subject = (thread.subject_normalized || "").toLowerCase();
      const summary = (thread.ai_summary_preview || "").toLowerCase();
      const snippet = (thread.snippet || "").toLowerCase();
      return (
        sender.includes(query) ||
        senderEmail.includes(query) ||
        subject.includes(query) ||
        summary.includes(query) ||
        snippet.includes(query)
      );
    });
  }, [searchQuery, threads]);

  const selectedThreads = useMemo(
    () => threads.filter((thread) => selectedThreadIds.has(thread.gmail_thread_id)),
    [threads, selectedThreadIds]
  );
  const hasSelectedThreads = selectedThreadIds.size > 0;
  const allVisibleSelected =
    filteredThreads.length > 0 &&
    filteredThreads.every((thread) => selectedThreadIds.has(thread.gmail_thread_id));

  const clearSelection = useCallback(() => {
    setSelectedThreadIds(new Set());
  }, []);

  const toggleThreadSelection = useCallback((threadId: string) => {
    setSelectedThreadIds((current) => {
      const next = new Set(current);
      if (next.has(threadId)) {
        next.delete(threadId);
      } else {
        next.add(threadId);
      }
      return next;
    });
  }, []);

  const selectAllVisible = useCallback(() => {
    setSelectedThreadIds(new Set(filteredThreads.map((thread) => thread.gmail_thread_id)));
  }, [filteredThreads]);

  const resetAndLoadFirstPage = useCallback(async () => {
    const nextContext = loadContextRef.current + 1;
    loadContextRef.current = nextContext;
    loadingMoreRef.current = false;
    setLoadingThreads(true);
    setLoadingMoreThreads(false);
    setError(null);
    try {
      const data = await fetchInboxThreads(activeTab, 1, THREAD_PAGE_SIZE);
      if (loadContextRef.current !== nextContext) return;
      setThreads(data.threads || []);
      setCurrentPage(data.page || 1);
      setHasMoreThreads(Boolean(data.has_more));
    } catch (err) {
      if (loadContextRef.current !== nextContext) return;
      setError(err instanceof Error ? err.message : "Failed to load inbox");
    } finally {
      if (loadContextRef.current !== nextContext) return;
      setLoadingThreads(false);
    }
  }, [activeTab]);

  const loadMoreThreads = useCallback(async () => {
    if (loadingThreads || loadingMoreRef.current || !hasMoreThreads) return;

    loadingMoreRef.current = true;
    setLoadingMoreThreads(true);
    const context = loadContextRef.current;
    const nextPage = currentPage + 1;

    try {
      const data = await fetchInboxThreads(activeTab, nextPage, THREAD_PAGE_SIZE);
      if (loadContextRef.current !== context) return;
      setThreads((prev) => mergeUniqueThreads(prev, data.threads || []));
      setCurrentPage(data.page || nextPage);
      setHasMoreThreads(Boolean(data.has_more));
    } catch (err) {
      if (loadContextRef.current !== context) return;
      setError(err instanceof Error ? err.message : "Failed to load more inbox threads");
    } finally {
      loadingMoreRef.current = false;
      if (loadContextRef.current !== context) return;
      setLoadingMoreThreads(false);
    }
  }, [activeTab, currentPage, hasMoreThreads, loadingThreads]);

  const loadThread = useCallback(async (threadId: string) => {
    setLoadingThreadDetail(true);
    setError(null);
    try {
      const data = await fetchInboxThread(threadId);
      const nextMessages = data.messages || [];
      setActiveThreadPreview(data.thread || null);
      setMessages(nextMessages);
      setExpandedMessageIds(() => {
        if (!nextMessages.length) return new Set();
        return new Set([nextMessages[nextMessages.length - 1].gmail_message_id]);
      });
      setAttachmentsByMessage(data.attachments_by_message || {});

      const unreadIds = nextMessages
        .filter((m) => !m.is_read)
        .slice(0, 10)
        .map((m) => m.gmail_message_id);

      if (unreadIds.length) {
        await Promise.all(unreadIds.map((id) => markInboxMessageRead(id)));
        setThreads((prev) =>
          prev.map((row) =>
            row.gmail_thread_id === threadId ? { ...row, has_unread: false } : row
          )
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load thread");
    } finally {
      setLoadingThreadDetail(false);
    }
  }, []);

  useEffect(() => {
    resetAndLoadFirstPage();
  }, [resetAndLoadFirstPage, refreshTick]);

  useEffect(() => {
    if (loadingThreads || !hasMoreThreads) return;
    const sentinel = listEndRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            void loadMoreThreads();
            break;
          }
        }
      },
      {
        root: null,
        rootMargin: "240px 0px",
      }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filteredThreads.length, hasMoreThreads, loadMoreThreads, loadingThreads]);

  useEffect(() => {
    if (!routeEmailId) return;
    if (activeThreadId === routeEmailId && isPreviewOpen) return;
    closeComposer();
    setActiveThreadId(routeEmailId);
    setIsPreviewOpen(true);
  }, [activeThreadId, isPreviewOpen, routeEmailId]);

  useEffect(() => {
    setSelectedThreadIds((current) => {
      if (current.size === 0) return current;
      const availableThreadIds = new Set(threads.map((thread) => thread.gmail_thread_id));
      const next = new Set(
        Array.from(current).filter((threadId) => availableThreadIds.has(threadId))
      );
      return next.size === current.size ? current : next;
    });
  }, [threads]);

  useEffect(() => {
    if (!isPreviewOpen || !activeThreadId) return;
    loadThread(activeThreadId);
  }, [isPreviewOpen, activeThreadId, loadThread]);

  useEffect(() => {
    if (!isPreviewOpen || loadingThreadDetail || messages.length === 0) return;
    const frame = window.requestAnimationFrame(() => {
      if (lastMessageRef.current) {
        lastMessageRef.current.scrollIntoView({ block: "end", behavior: "smooth" });
      } else if (threadScrollRef.current) {
        threadScrollRef.current.scrollTop = threadScrollRef.current.scrollHeight;
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isPreviewOpen, loadingThreadDetail, messages, activeThreadId]);

  useEffect(() => {
    if (!pendingComposerMode || !latestMessage || !isPreviewOpen) return;
    setPendingComposerMode(null);
    if (pendingComposerMode === "reply" || pendingComposerMode === "forward") {
      openComposer(pendingComposerMode);
    }
  }, [pendingComposerMode, latestMessage, isPreviewOpen]);

  useEffect(() => {
    if (!isPreviewOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closePreview();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isPreviewOpen]);

  const openComposer = (mode: ComposerMode) => {
    setComposerMode(mode);
    setComposeCc("");
    if (mode === "new") {
      setComposeTo("");
      setComposeSubject("");
      setComposeBody("");
      return;
    }
    const from = latestMessage?.from_json?.email || "";
    const subject = latestMessage?.subject || "";
    if (mode === "reply") {
      setComposeTo(from);
      setComposeSubject(subject.toLowerCase().startsWith("re:") ? subject : `Re: ${subject}`);
      setComposeBody("");
      return;
    }
    setComposeTo("");
    setComposeSubject(subject.toLowerCase().startsWith("fwd:") ? subject : `Fwd: ${subject}`);
    setComposeBody("");
  };

  const closeComposer = () => {
    setComposerMode(null);
    setPendingComposerMode(null);
    setComposeBody("");
    setComposeCc("");
    setComposeTo("");
    setComposeSubject("");
  };

  const closePreview = () => {
    syncInboxUrl(null);
    closeComposer();
    setIsPreviewOpen(false);
    setActiveThreadId(null);
    setActiveThreadPreview(null);
    setMessages([]);
    setExpandedMessageIds(new Set());
    setAttachmentsByMessage({});
  };

  const openThreadPreview = (threadId: string, mode: ComposerMode | null = null) => {
    syncInboxUrl(threadId);
    setActiveThreadId(threadId);
    setActiveThreadPreview(null);
    setIsPreviewOpen(true);
    closeComposer();
    if (mode) {
      setPendingComposerMode(mode);
    }
  };

  const openNewMessageModal = () => {
    syncInboxUrl(null);
    setActiveThreadId(null);
    setActiveThreadPreview(null);
    setMessages([]);
    setExpandedMessageIds(new Set());
    setAttachmentsByMessage({});
    setIsPreviewOpen(true);
    openComposer("new");
  };

  const toggleExpandedMessage = (messageId: string, isLastMessage: boolean) => {
    if (isLastMessage) return;
    setExpandedMessageIds((current) => {
      const next = new Set(current);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  };

  const submitComposer = async () => {
    if (sending) return;
    setSending(true);
    setError(null);
    try {
      if (composerMode === "new") {
        await sendInboxEmail({
          to: composeTo,
          subject: composeSubject,
          body: composeBody,
          cc: composeCc || undefined,
        });
      } else if (composerMode === "reply") {
        if (!latestMessage?.gmail_message_id) throw new Error("Select a thread first");
        await replyInboxEmail({
          message_id: latestMessage.gmail_message_id,
          body: composeBody,
          cc: composeCc || undefined,
        });
      } else if (composerMode === "forward") {
        if (!latestMessage?.gmail_message_id) throw new Error("Select a thread first");
        await forwardInboxEmail({
          message_id: latestMessage.gmail_message_id,
          to: composeTo,
          body: composeBody,
          cc: composeCc || undefined,
        });
      }

      const sentMode = composerMode;
      closeComposer();
      if (sentMode === "new") {
        closePreview();
      } else if (activeThreadId) {
        await loadThread(activeThreadId);
      }
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send email");
    } finally {
      setSending(false);
    }
  };

  const archiveThread = async (threadId: string) => {
    if (archivingThreadId) return;
    setArchivingThreadId(threadId);
    setError(null);
    try {
      if (activeTab === "drafts") {
        await discardInboxThreadDrafts(threadId);
      } else {
        await archiveInboxThread(threadId);
      }
      if (activeThreadId === threadId) {
        closePreview();
      }
      setSelectedThreadIds((current) => {
        if (!current.has(threadId)) return current;
        const next = new Set(current);
        next.delete(threadId);
        return next;
      });
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : activeTab === "drafts"
          ? "Failed to discard draft thread"
          : "Failed to archive thread"
      );
    } finally {
      setArchivingThreadId(null);
    }
  };

  const submitBulkPrompt = async () => {
    const prompt = bulkPrompt.trim();
    if (!prompt || isBulkSending || selectedThreads.length === 0) return;

    setIsBulkSending(true);
    setError(null);
    try {
      const contextBlock = buildSelectedThreadsContext(selectedThreads);
      const message = `${contextBlock}\n\nUser request:\n${prompt}`;
      const conversation = await createConversation("Inbox Agent Chat");
      const params = new URLSearchParams({ q: message });
      if (selectedSkillName) {
        params.set("skill", selectedSkillName);
      }
      router.push(`/chat/${conversation.id}?${params.toString()}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start agent chat");
    } finally {
      setIsBulkSending(false);
    }
  };

  const handleRefresh = () => {
    clearSelection();
    setRefreshTick((n) => n + 1);
  };

  const handleTabChange = (tab: InboxTab) => {
    setActiveTab(tab);
    clearSelection();
  };

  const sendSelectedDraft = async () => {
    if (!selectedDraftMessage || sendingDraft) return;
    setSendingDraft(true);
    setError(null);
    try {
      await sendInboxDraft(selectedDraftMessage.gmail_message_id);
      if (activeThreadId) {
        await loadThread(activeThreadId);
      }
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send draft");
    } finally {
      setSendingDraft(false);
    }
  };

  const runAttachmentAction = (
    key: string,
    action: "downloading" | "saving" | "saved" | null
  ) => {
    setAttachmentActions((prev) => {
      const next = { ...prev };
      if (action) {
        next[key] = action;
      } else {
        delete next[key];
      }
      return next;
    });
  };

  const handleDownloadAttachment = async (
    messageId: string,
    attachment: EmailAttachment
  ) => {
    const key = `${messageId}:${attachment.gmail_attachment_id}`;
    runAttachmentAction(key, "downloading");
    setError(null);
    try {
      const { blob, filename } = await downloadInboxAttachment(
        messageId,
        attachment.gmail_attachment_id
      );
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename || attachment.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to download attachment");
    } finally {
      runAttachmentAction(key, null);
    }
  };

  const handleSaveAttachment = async (
    messageId: string,
    attachment: EmailAttachment
  ) => {
    const key = `${messageId}:${attachment.gmail_attachment_id}`;
    runAttachmentAction(key, "saving");
    setError(null);
    try {
      await saveInboxAttachmentToDocuments(messageId, attachment.gmail_attachment_id);
      runAttachmentAction(key, "saved");
      window.setTimeout(() => runAttachmentAction(key, null), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save attachment");
      runAttachmentAction(key, null);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-6">
        <div className="mb-4 flex items-center gap-2">
          <Inbox size={18} className="text-blue-400" strokeWidth={1.5} />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Inbox</h1>
        </div>

        {error && (
          <div className="mb-4 rounded-xl bg-red-400/[0.08] px-4 py-2 text-sm text-red-400/90">
            {error}
          </div>
        )}

        <div className="rounded-2xl border border-foreground/[0.08] bg-card/70 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <label className="relative block flex-1">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-foreground/45"
              />
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search sender, subject, summary, or snippet"
                className="w-full rounded-xl border border-foreground/[0.1] bg-background/70 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-400/60"
              />
            </label>
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={handleRefresh}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.04]"
              >
                <RefreshCw size={12} />
                Refresh
              </button>
              <button
                onClick={openNewMessageModal}
                className="inline-flex items-center gap-1 rounded-lg bg-blue-500 px-3 py-2 text-xs font-medium text-white hover:bg-blue-400"
              >
                <MailPlus size={12} />
                New
              </button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`rounded-lg px-2.5 py-1.5 text-xs ${
                  activeTab === tab.id
                    ? "bg-blue-500/15 text-blue-400"
                    : "text-foreground/60 hover:bg-foreground/[0.04] hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            ))}
            <div className="ml-auto flex items-center gap-1.5">
              <button
                onClick={allVisibleSelected ? clearSelection : selectAllVisible}
                disabled={filteredThreads.length === 0}
                className="rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.04] disabled:opacity-50"
              >
                {allVisibleSelected ? "Clear visible" : "Select visible"}
              </button>
              {hasSelectedThreads && (
                <button
                  onClick={clearSelection}
                  className="rounded-lg px-2.5 py-1.5 text-xs text-foreground/70 hover:bg-foreground/[0.04]"
                >
                  Clear ({selectedThreadIds.size})
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 overflow-hidden rounded-2xl border border-foreground/[0.08] bg-card/70">
          {loadingThreads ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={18} className="animate-spin text-foreground/30" />
            </div>
          ) : filteredThreads.length === 0 ? (
            <div className="px-4 py-12 text-sm text-foreground/50">
              {threads.length === 0
                ? "No threads yet."
                : searchQuery.trim() && hasMoreThreads
                ? "No loaded emails matched your search yet. Keep scrolling to load more."
                : "No emails matched your search."}
            </div>
          ) : (
            <div className="divide-y divide-foreground/[0.06]">
              {filteredThreads.map((thread) => {
                const isSelected = selectedThreadIds.has(thread.gmail_thread_id);
                return (
                <article
                  key={thread.gmail_thread_id}
                  className={`group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-foreground/[0.03] ${
                    isSelected ? "bg-blue-500/[0.08]" : ""
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => toggleThreadSelection(thread.gmail_thread_id)}
                    className={`mt-1 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                      isSelected
                        ? "border-blue-400 bg-blue-500 text-white"
                        : "border-foreground/25 bg-background text-transparent hover:border-foreground/45"
                    }`}
                    aria-label={isSelected ? "Deselect thread" : "Select thread"}
                  >
                    <Check size={11} />
                  </button>
                  <button
                    onClick={() => openThreadPreview(thread.gmail_thread_id)}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left"
                  >
                    {thread.has_unread ? (
                      <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-blue-400" />
                    ) : (
                      <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-transparent" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {getSenderLabel(thread)}
                        </p>
                        <p className="truncate text-sm text-foreground/75">
                          {thread.subject_normalized || "(No subject)"}
                        </p>
                        {thread.has_attachments && (
                          <Paperclip size={13} className="shrink-0 text-foreground/50" />
                        )}
                      </div>
                      <p className="mt-1 line-clamp-1 text-xs text-foreground/55">
                        {thread.ai_summary_preview || thread.snippet}
                      </p>
                    </div>
                    <p className="shrink-0 text-[11px] text-foreground/45">
                      {formatTime(thread.last_message_internal_at)}
                    </p>
                  </button>

                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        openThreadPreview(thread.gmail_thread_id, "reply");
                      }}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.05]"
                    >
                      <Reply size={11} />
                      Reply
                    </button>
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        archiveThread(thread.gmail_thread_id);
                      }}
                      disabled={archivingThreadId === thread.gmail_thread_id}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.05] disabled:opacity-50"
                    >
                      {archivingThreadId === thread.gmail_thread_id ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : activeTab === "drafts" ? (
                        <Trash2 size={11} />
                      ) : (
                        <Archive size={11} />
                      )}
                      {activeTab === "drafts" ? "Discard" : "Archive"}
                    </button>
                  </div>
                </article>
                );
              })}
            </div>
          )}
          {!loadingThreads && threads.length > 0 && (
            <div
              ref={listEndRef}
              className="flex min-h-12 items-center justify-center border-t border-foreground/[0.06] px-3 py-3 text-xs text-foreground/50"
            >
              {loadingMoreThreads ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 size={13} className="animate-spin" />
                  Loading more threads...
                </span>
              ) : hasMoreThreads ? (
                "Scroll to load more"
              ) : (
                "No more threads"
              )}
            </div>
          )}
        </div>
      </div>

      {hasSelectedThreads && (
        <div className="pointer-events-none fixed inset-x-0 bottom-[4.5rem] z-40 px-3 md:bottom-4 md:px-6">
          <div className="pointer-events-auto mx-auto w-full max-w-5xl rounded-2xl border border-blue-400/30 bg-background/95 p-3 shadow-2xl backdrop-blur">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-xs text-foreground/70">
                {selectedThreadIds.size} selected thread{selectedThreadIds.size === 1 ? "" : "s"}
              </p>
              <button
                onClick={clearSelection}
                className="rounded-md px-2 py-1 text-xs text-foreground/60 hover:bg-foreground/[0.06]"
              >
                Clear
              </button>
            </div>
            <textarea
              value={bulkPrompt}
              onChange={(event) => setBulkPrompt(event.target.value)}
              placeholder="Ask the agent to analyze or act on the selected inbox threads..."
              rows={3}
              className="w-full resize-y rounded-xl border border-foreground/[0.12] bg-background px-3 py-2 text-sm outline-none focus:border-blue-400/60"
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <Popover open={skillsOpen} onOpenChange={setSkillsOpen}>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 rounded-full px-2.5 text-xs text-blue-500 hover:bg-blue-500/10 hover:text-blue-500"
                    disabled={isBulkSending}
                  >
                    <Sparkles size={13} />
                    <span className="max-w-[12rem] truncate">
                      {selectedSkillName || "Skills"}
                    </span>
                    <ChevronDown size={12} />
                  </Button>
                </PopoverTrigger>
                <PopoverContent
                  side="top"
                  align="start"
                  className="w-[18rem] rounded-xl border-foreground/[0.12] p-1.5"
                >
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedSkillName(null);
                      setSkillsOpen(false);
                    }}
                    className="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm text-foreground/80 transition-colors hover:bg-foreground/[0.06]"
                  >
                    <span>Default (no skill)</span>
                    {!selectedSkillName ? <Check size={14} className="text-blue-500" /> : null}
                  </button>
                  {skillsLoading ? (
                    <p className="px-2.5 py-2 text-xs text-foreground/45">Loading skills...</p>
                  ) : enabledSkills.length > 0 ? (
                    enabledSkills.map((skill) => (
                      <button
                        key={skill.id}
                        type="button"
                        onClick={() => {
                          setSelectedSkillName(skill.name);
                          setSkillsOpen(false);
                        }}
                        className="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm text-foreground/80 transition-colors hover:bg-foreground/[0.06]"
                      >
                        <span className="truncate">{skill.name}</span>
                        {selectedSkillName === skill.name ? (
                          <Check size={14} className="text-blue-500" />
                        ) : null}
                      </button>
                    ))
                  ) : (
                    <p className="px-2.5 py-2 text-xs text-foreground/45">No active skills found</p>
                  )}
                </PopoverContent>
              </Popover>
              <button
                onClick={submitBulkPrompt}
                disabled={isBulkSending || !bulkPrompt.trim() || selectedThreadIds.size === 0}
                className="inline-flex h-9 items-center gap-1 rounded-full bg-blue-500 px-3 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-50"
              >
                {isBulkSending ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={14} />}
                Send
              </button>
            </div>
          </div>
        </div>
      )}

      {isPreviewOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/35 glass-subtle"
          onClick={closePreview}
        >
          <div className="mx-auto flex h-full w-full max-w-6xl items-center px-4 py-6">
            <section
              onClick={(event) => event.stopPropagation()}
              className="relative flex h-full w-full flex-col overflow-hidden rounded-3xl border border-foreground/[0.12] bg-background/85 shadow-2xl backdrop-blur-xl"
            >
              <header className="sticky top-0 z-20 border-b border-foreground/[0.08] bg-background/85 px-5 py-3">
                <div className="flex flex-col gap-3">
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-foreground">
                        {selectedThread?.subject_normalized || "New message"}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      {selectedThread && (
                        <>
                          <button
                            onClick={() => openComposer("reply")}
                            disabled={!latestMessage}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.12] disabled:opacity-40"
                          >
                            <Reply size={12} />
                            Reply
                          </button>
                          <button
                            onClick={() => openComposer("forward")}
                            disabled={!latestMessage}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.12] disabled:opacity-40"
                          >
                            <Forward size={12} />
                            Forward
                          </button>
                          {(hasDraftMessages || activeTab === "drafts") && (
                            <button
                              onClick={sendSelectedDraft}
                              disabled={!selectedDraftMessage || sendingDraft}
                              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.12] disabled:opacity-40"
                            >
                              {sendingDraft ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                <Send size={12} />
                              )}
                              Send Draft
                            </button>
                          )}
                          <button
                            onClick={() => selectedThread && archiveThread(selectedThread.gmail_thread_id)}
                            disabled={!selectedThread || archivingThreadId === selectedThread.gmail_thread_id}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.12] disabled:opacity-40"
                          >
                            {archivingThreadId === selectedThread.gmail_thread_id ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : activeTab === "drafts" || hasDraftMessages ? (
                              <Trash2 size={12} />
                            ) : (
                              <Archive size={12} />
                            )}
                            {activeTab === "drafts" || hasDraftMessages ? "Discard" : "Archive"}
                          </button>
                        </>
                      )}

                      <button
                        onClick={closePreview}
                        className="rounded-lg p-1.5 text-foreground/70 hover:bg-foreground/[0.06]"
                        aria-label="Close preview"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </div>

                  {selectedThread && (
                    <div className="my-2 px-2 md:my-3 md:px-3">
                      <div className="relative mx-auto w-full max-w-4xl overflow-hidden rounded-3xl border border-blue-300/30 bg-[radial-gradient(circle_at_50%_0%,rgba(96,165,250,0.3),rgba(59,130,246,0.09)_42%,rgba(15,23,42,0.04)_100%)] px-6 py-6 shadow-[0_22px_70px_-34px_rgba(59,130,246,0.95)] md:px-8 md:py-7">
                        <div className="pointer-events-none absolute inset-x-12 top-0 h-20 rounded-full bg-blue-300/20 blur-3xl" />
                        <div className="pointer-events-none absolute -left-14 top-1/2 h-28 w-28 -translate-y-1/2 rounded-full bg-indigo-300/10 blur-3xl" />
                        <div className="pointer-events-none absolute -right-14 top-1/2 h-28 w-28 -translate-y-1/2 rounded-full bg-cyan-300/10 blur-3xl" />
                        <div className="relative">
                          <div className="mb-3 flex items-center justify-center gap-2 text-blue-200/95">
                            <Sparkles size={15} />
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em]">
                              AI-Generated Thread Summary
                            </p>
                          </div>
                          <p className="mx-auto max-w-3xl text-center text-[15px] leading-relaxed text-foreground/95">
                            {selectedThread.ai_summary_preview ||
                              selectedThread.snippet ||
                              "No summary available."}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </header>

              <div ref={threadScrollRef} className="flex-1 overflow-y-auto p-5">
                {loadingThreadDetail ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 size={18} className="animate-spin text-foreground/30" />
                  </div>
                ) : !selectedThread && composerMode === "new" ? (
                  <div className="text-sm text-foreground/60">Compose a new message.</div>
                ) : !selectedThread ? (
                  <div className="text-sm text-foreground/60">Select an email to preview.</div>
                ) : messages.length === 0 ? (
                  <div className="text-sm text-foreground/60">No messages synced for this thread yet.</div>
                ) : (
                  <div className="space-y-4">
                    {messages.map((message, index) => {
                      const isLastMessage = index === messages.length - 1;
                      const isExpanded = expandedMessageIds.has(message.gmail_message_id);
                      return (
                      <article
                        key={message.gmail_message_id}
                        ref={isLastMessage ? lastMessageRef : null}
                        className="rounded-2xl border border-foreground/[0.09] bg-card/90 p-4"
                      >
                        <button
                          type="button"
                          onClick={() =>
                            toggleExpandedMessage(message.gmail_message_id, isLastMessage)
                          }
                          className="flex w-full items-center justify-between gap-2 rounded-lg px-1 py-0.5 text-left hover:bg-foreground/[0.04]"
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            {isExpanded ? (
                              <ChevronDown size={15} className="shrink-0 text-foreground/60" />
                            ) : (
                              <ChevronRight size={15} className="shrink-0 text-foreground/60" />
                            )}
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium text-foreground">
                                {message.from_json?.name || message.from_json?.email || "Unknown sender"}
                              </p>
                              {message.from_json?.email && (
                                <p className="truncate text-xs font-mono text-foreground/65">
                                  {message.from_json.email}
                                </p>
                              )}
                            </div>
                          </div>
                          <p className="text-xs text-foreground/50">
                            {message.internal_date_ts
                              ? new Date(message.internal_date_ts).toLocaleString()
                              : ""}
                          </p>
                        </button>

                        {!isExpanded && (
                          <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-foreground/60">
                            {getCollapsedMessagePreview(message)}
                          </p>
                        )}

                        {isExpanded && (
                          <>
                            <p className="mt-2 text-xs text-foreground/55">
                              To: {(message.to_json || []).map((recipient) => recipient.email).join(", ")}
                            </p>
                            {(message.cc_json || []).length > 0 && (
                              <p className="mt-1 text-xs text-foreground/55">
                                Cc: {(message.cc_json || []).map((recipient) => recipient.email).join(", ")}
                              </p>
                            )}

                            {message.body_html_sanitized ? (
                              <iframe
                                title={`email-preview-${message.gmail_message_id}`}
                                className="mt-3 h-[520px] w-full rounded-xl border border-foreground/[0.08] bg-white isolate"
                                sandbox="allow-popups allow-popups-to-escape-sandbox"
                                style={{ contain: "strict" }}
                                srcDoc={buildEmailHtmlDoc(message.subject, message.body_html_sanitized)}
                              />
                            ) : (
                              <p className="mt-3 whitespace-pre-wrap text-xs text-foreground/65">
                                {message.body_text || message.snippet || "(No content)"}
                              </p>
                            )}

                            {(attachmentsByMessage[message.gmail_message_id] || []).length > 0 && (
                              <div className="mt-3 flex flex-col gap-2">
                                {(attachmentsByMessage[message.gmail_message_id] || []).map((attachment) => (
                                  <div
                                    key={`${attachment.gmail_attachment_id}-${attachment.filename}`}
                                    className="rounded-lg bg-foreground/[0.05] px-2.5 py-2 text-[11px] text-foreground/70"
                                    title={attachment.mime_type}
                                  >
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <span className="truncate">
                                        {attachment.filename} · {formatBytes(attachment.size_bytes)}
                                      </span>
                                      <div className="flex items-center gap-1.5">
                                        <button
                                          onClick={() =>
                                            handleDownloadAttachment(message.gmail_message_id, attachment)
                                          }
                                          disabled={
                                            attachmentActions[
                                              `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                            ] === "downloading" ||
                                            attachmentActions[
                                              `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                            ] === "saving"
                                          }
                                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.06] disabled:opacity-50"
                                        >
                                          {attachmentActions[
                                            `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                          ] === "downloading" ? (
                                            <Loader2 size={11} className="animate-spin" />
                                          ) : (
                                            <Download size={11} />
                                          )}
                                          Download
                                        </button>
                                        <button
                                          onClick={() =>
                                            handleSaveAttachment(message.gmail_message_id, attachment)
                                          }
                                          disabled={
                                            attachmentActions[
                                              `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                            ] === "downloading" ||
                                            attachmentActions[
                                              `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                            ] === "saving"
                                          }
                                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.06] disabled:opacity-50"
                                        >
                                          {attachmentActions[
                                            `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                          ] === "saving" ? (
                                            <Loader2 size={11} className="animate-spin" />
                                          ) : attachmentActions[
                                              `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                            ] === "saved" ? (
                                            <Check size={11} />
                                          ) : (
                                            <FolderPlus size={11} />
                                          )}
                                          {attachmentActions[
                                            `${message.gmail_message_id}:${attachment.gmail_attachment_id}`
                                          ] === "saved"
                                            ? "Saved"
                                            : "Save to Documents"}
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </article>
                    );
                    })}
                  </div>
                )}

                {composerMode && (
                  <article className="mt-4 rounded-2xl border border-blue-400/30 bg-card p-4">
                    <h2 className="mb-3 text-sm font-semibold text-foreground">
                      {composerMode === "new"
                        ? "New Email"
                        : composerMode === "reply"
                        ? "Reply in Thread"
                        : "Forward Message"}
                    </h2>
                    {(composerMode === "new" || composerMode === "forward") && (
                      <input
                        value={composeTo}
                        onChange={(event) => setComposeTo(event.target.value)}
                        placeholder="To"
                        className="mb-2 w-full rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
                      />
                    )}
                    {composerMode === "reply" && (
                      <div className="mb-2 rounded-xl bg-blue-500/[0.08] px-3 py-2 ring-1 ring-blue-400/20">
                        <p className="text-[11px] uppercase tracking-wide text-blue-300/90">
                          To (replying to sender)
                        </p>
                        <p className="text-sm font-medium text-foreground">
                          {composeTo || "Unknown sender"}
                        </p>
                      </div>
                    )}
                    <input
                      value={composeCc}
                      onChange={(event) => setComposeCc(event.target.value)}
                      placeholder="Cc (optional)"
                      className="mb-2 w-full rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
                    />
                    <input
                      value={composeSubject}
                      onChange={(event) => setComposeSubject(event.target.value)}
                      placeholder="Subject"
                      disabled={composerMode === "reply"}
                      className="mb-2 w-full rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2] disabled:opacity-50"
                    />
                    <textarea
                      value={composeBody}
                      onChange={(event) => setComposeBody(event.target.value)}
                      placeholder={
                        composerMode === "reply" || composerMode === "forward"
                          ? "Write ruslan@floatfinancial.com response to the thread..."
                          : "Write your message..."
                      }
                      rows={6}
                      className="w-full rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
                    />
                    <div className="mt-4 flex justify-end gap-2">
                      <button
                        onClick={closeComposer}
                        className="rounded-lg px-3 py-2 text-sm text-foreground/70 hover:bg-foreground/[0.05]"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={submitComposer}
                        disabled={
                          sending ||
                          !composeBody.trim() ||
                          ((composerMode === "new" || composerMode === "forward") &&
                            !composeTo.trim())
                        }
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                        Send
                      </button>
                    </div>
                  </article>
                )}
              </div>

              <footer className="sticky bottom-0 z-20 border-t border-foreground/[0.08] bg-background/85 px-5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-foreground/55">Quick actions</p>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => openComposer("reply")}
                      disabled={!selectedThread || !latestMessage}
                      className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs ring-1 ring-foreground/[0.12] disabled:opacity-40"
                    >
                      <Reply size={12} />
                      Reply
                    </button>
                    <button
                      onClick={() => openComposer("forward")}
                      disabled={!selectedThread || !latestMessage}
                      className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs ring-1 ring-foreground/[0.12] disabled:opacity-40"
                    >
                      <Forward size={12} />
                      Forward
                    </button>
                  </div>
                </div>
              </footer>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

export default function InboxPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[50vh] items-center justify-center px-4 text-sm text-foreground/70">
          Loading inbox...
        </div>
      }
    >
      <InboxPageContent />
    </Suspense>
  );
}
