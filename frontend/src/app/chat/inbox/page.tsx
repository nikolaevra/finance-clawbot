"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Inbox,
  Loader2,
  MailPlus,
  Reply,
  Forward,
  Send,
  RefreshCw,
} from "lucide-react";
import type { EmailAttachment, EmailMessage, EmailThread, InboxTab } from "@/types";
import {
  fetchInboxThread,
  fetchInboxThreads,
  forwardInboxEmail,
  markInboxMessageRead,
  replyInboxEmail,
  sendInboxEmail,
} from "@/lib/api";

type ComposerMode = "new" | "reply" | "forward";

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

export default function InboxPage() {
  const [activeTab, setActiveTab] = useState<InboxTab>("inbox");
  const [threads, setThreads] = useState<EmailThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [attachmentsByMessage, setAttachmentsByMessage] = useState<Record<string, EmailAttachment[]>>(
    {}
  );
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingThreadDetail, setLoadingThreadDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  const [composerOpen, setComposerOpen] = useState(false);
  const [composerMode, setComposerMode] = useState<ComposerMode>("new");
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeCc, setComposeCc] = useState("");

  const selectedThread = useMemo(
    () => threads.find((t) => t.gmail_thread_id === selectedThreadId) || null,
    [threads, selectedThreadId]
  );
  const latestMessage = messages[messages.length - 1];

  const loadThreads = useCallback(async () => {
    setLoadingThreads(true);
    setError(null);
    try {
      const data = await fetchInboxThreads(activeTab, 1, 50);
      setThreads(data.threads || []);
      if ((data.threads || []).length === 0) {
        setSelectedThreadId(null);
        setMessages([]);
        setAttachmentsByMessage({});
      } else if (!selectedThreadId || !(data.threads || []).some((t) => t.gmail_thread_id === selectedThreadId)) {
        setSelectedThreadId(data.threads[0].gmail_thread_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load inbox");
    } finally {
      setLoadingThreads(false);
    }
  }, [activeTab, selectedThreadId]);

  const loadThread = useCallback(async () => {
    if (!selectedThreadId) return;
    setLoadingThreadDetail(true);
    setError(null);
    try {
      const data = await fetchInboxThread(selectedThreadId);
      setMessages(data.messages || []);
      setAttachmentsByMessage(data.attachments_by_message || {});

      const unreadIds = (data.messages || [])
        .filter((m) => !m.is_read)
        .slice(0, 10)
        .map((m) => m.gmail_message_id);
      if (unreadIds.length) {
        await Promise.all(unreadIds.map((id) => markInboxMessageRead(id)));
        setThreads((prev) =>
          prev.map((row) =>
            row.gmail_thread_id === selectedThreadId
              ? { ...row, has_unread: false }
              : row
          )
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load thread");
    } finally {
      setLoadingThreadDetail(false);
    }
  }, [selectedThreadId]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads, refreshTick]);

  useEffect(() => {
    loadThread();
  }, [loadThread]);

  const openComposer = (mode: ComposerMode) => {
    setComposerMode(mode);
    setComposerOpen(true);
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
      } else {
        if (!latestMessage?.gmail_message_id) throw new Error("Select a thread first");
        await forwardInboxEmail({
          message_id: latestMessage.gmail_message_id,
          to: composeTo,
          body: composeBody,
          cc: composeCc || undefined,
        });
      }
      setComposerOpen(false);
      setComposeBody("");
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send email");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-5 border-b border-foreground/[0.08]">
        <Inbox size={18} className="text-blue-400" strokeWidth={1.5} />
        <h1 className="text-lg font-semibold text-foreground tracking-tight">Inbox</h1>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setRefreshTick((n) => n + 1)}
            className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs ring-1 ring-foreground/[0.08] hover:bg-foreground/[0.04]"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
          <button
            onClick={() => openComposer("new")}
            className="inline-flex items-center gap-1 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-400"
          >
            <MailPlus size={12} />
            New
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 rounded-xl bg-red-400/[0.08] px-4 py-2 text-sm text-red-400/90">
          {error}
        </div>
      )}

      <div className="grid h-full grid-cols-[320px_1fr] overflow-hidden">
        <aside className="border-r border-foreground/[0.08] overflow-hidden flex flex-col">
          <div className="flex items-center gap-1 p-3 border-b border-foreground/[0.08]">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`rounded-lg px-2.5 py-1.5 text-xs ${
                  activeTab === tab.id
                    ? "bg-blue-500/15 text-blue-400"
                    : "text-foreground/60 hover:text-foreground hover:bg-foreground/[0.04]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto">
            {loadingThreads ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 size={18} className="animate-spin text-foreground/30" />
              </div>
            ) : threads.length === 0 ? (
              <div className="px-4 py-8 text-sm text-foreground/50">No threads yet.</div>
            ) : (
              <div className="divide-y divide-foreground/[0.06]">
                {threads.map((thread) => (
                  <button
                    key={thread.gmail_thread_id}
                    onClick={() => setSelectedThreadId(thread.gmail_thread_id)}
                    className={`w-full text-left px-4 py-3 transition-colors ${
                      selectedThreadId === thread.gmail_thread_id
                        ? "bg-foreground/[0.06]"
                        : "hover:bg-foreground/[0.03]"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <p className="line-clamp-1 text-sm font-medium text-foreground">
                        {thread.subject_normalized || "(No subject)"}
                      </p>
                      {thread.has_unread && (
                        <span className="h-2 w-2 rounded-full bg-blue-400 shrink-0" />
                      )}
                    </div>
                    <p className="line-clamp-1 text-xs text-foreground/50 mt-1">{thread.snippet}</p>
                    <p className="text-[11px] text-foreground/40 mt-1">
                      {formatTime(thread.last_message_internal_at)}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <section className="flex h-full flex-col overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-foreground/[0.08]">
            <p className="text-sm font-medium text-foreground truncate">
              {selectedThread?.subject_normalized || "Select a thread"}
            </p>
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={() => openComposer("reply")}
                disabled={!selectedThread || !latestMessage}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.08] disabled:opacity-40"
              >
                <Reply size={12} />
                Reply
              </button>
              <button
                onClick={() => openComposer("forward")}
                disabled={!selectedThread || !latestMessage}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.08] disabled:opacity-40"
              >
                <Forward size={12} />
                Forward
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {loadingThreadDetail ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 size={18} className="animate-spin text-foreground/30" />
              </div>
            ) : !selectedThread ? (
              <div className="text-sm text-foreground/50">Pick a thread to view messages.</div>
            ) : messages.length === 0 ? (
              <div className="text-sm text-foreground/50">No messages synced for this thread yet.</div>
            ) : (
              messages.map((message) => (
                <article
                  key={message.gmail_message_id}
                  className="rounded-2xl ring-1 ring-foreground/[0.08] bg-card p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-foreground">
                      {message.from_json?.name || message.from_json?.email || "Unknown sender"}
                    </p>
                    <p className="text-xs text-foreground/50">
                      {message.internal_date_ts
                        ? new Date(message.internal_date_ts).toLocaleString()
                        : ""}
                    </p>
                  </div>
                  <p className="text-xs text-foreground/50 mt-1">
                    To: {(message.to_json || []).map((r) => r.email).join(", ")}
                  </p>
                  {(message.cc_json || []).length > 0 && (
                    <p className="text-xs text-foreground/50 mt-1">
                      Cc: {(message.cc_json || []).map((r) => r.email).join(", ")}
                    </p>
                  )}
                  {message.body_html_sanitized ? (
                    <div
                      className="mt-3 text-sm text-foreground/75 leading-6 overflow-x-auto [&_a]:text-blue-400 [&_a]:underline [&_blockquote]:border-l [&_blockquote]:border-foreground/20 [&_blockquote]:pl-3 [&_img]:max-w-full [&_img]:h-auto [&_pre]:whitespace-pre-wrap [&_table]:w-full [&_td]:align-top [&_th]:align-top"
                      dangerouslySetInnerHTML={{ __html: message.body_html_sanitized }}
                    />
                  ) : (
                    <p className="text-xs text-foreground/60 mt-3 whitespace-pre-wrap">
                      {message.body_text || message.snippet || "(No content)"}
                    </p>
                  )}
                  {(attachmentsByMessage[message.gmail_message_id] || []).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(attachmentsByMessage[message.gmail_message_id] || []).map((attachment) => (
                        <div
                          key={`${attachment.gmail_attachment_id}-${attachment.filename}`}
                          className="rounded-lg bg-foreground/[0.05] px-2.5 py-1.5 text-[11px] text-foreground/70"
                          title={attachment.mime_type}
                        >
                          {attachment.filename} · {formatBytes(attachment.size_bytes)}
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))
            )}
          </div>
        </section>
      </div>

      {composerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="w-full max-w-2xl rounded-2xl bg-card ring-1 ring-foreground/[0.08] p-5">
            <h2 className="text-sm font-semibold text-foreground mb-4">
              {composerMode === "new"
                ? "New Email"
                : composerMode === "reply"
                ? "Reply"
                : "Forward"}
            </h2>
            {(composerMode === "new" || composerMode === "forward") && (
              <input
                value={composeTo}
                onChange={(e) => setComposeTo(e.target.value)}
                placeholder="To"
                className="w-full mb-2 rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
              />
            )}
            <input
              value={composeCc}
              onChange={(e) => setComposeCc(e.target.value)}
              placeholder="Cc (optional)"
              className="w-full mb-2 rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
            />
            <input
              value={composeSubject}
              onChange={(e) => setComposeSubject(e.target.value)}
              placeholder="Subject"
              disabled={composerMode === "reply"}
              className="w-full mb-2 rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2] disabled:opacity-50"
            />
            <textarea
              value={composeBody}
              onChange={(e) => setComposeBody(e.target.value)}
              placeholder="Write your message..."
              rows={8}
              className="w-full rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setComposerOpen(false)}
                className="rounded-lg px-3 py-2 text-sm text-foreground/70 hover:bg-foreground/[0.05]"
              >
                Cancel
              </button>
              <button
                onClick={submitComposer}
                disabled={sending || !composeBody.trim()}
                className="inline-flex items-center gap-1 rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
