"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive,
  Inbox,
  Loader2,
  MailPlus,
  Reply,
  Forward,
  Send,
  RefreshCw,
  Download,
  FolderPlus,
  Check,
} from "lucide-react";
import type { EmailAttachment, EmailMessage, EmailThread, InboxTab } from "@/types";
import {
  fetchInboxThread,
  fetchInboxThreads,
  forwardInboxEmail,
  archiveInboxThread,
  markInboxMessageRead,
  replyInboxEmail,
  sendInboxEmail,
  downloadInboxAttachment,
  saveInboxAttachmentToDocuments,
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
  const [archiving, setArchiving] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [attachmentActions, setAttachmentActions] = useState<Record<string, "downloading" | "saving" | "saved">>({});

  const [composerMode, setComposerMode] = useState<ComposerMode | null>(null);
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
      const nextThreads = data.threads || [];
      setThreads(nextThreads);
      if (nextThreads.length === 0) {
        setSelectedThreadId(null);
        setMessages([]);
        setAttachmentsByMessage({});
      } else {
        setSelectedThreadId((prevSelectedThreadId) => {
          if (
            prevSelectedThreadId &&
            nextThreads.some((thread) => thread.gmail_thread_id === prevSelectedThreadId)
          ) {
            return prevSelectedThreadId;
          }
          return nextThreads[0].gmail_thread_id;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load inbox");
    } finally {
      setLoadingThreads(false);
    }
  }, [activeTab]);

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
    setComposeBody("");
    setComposeCc("");
    setComposeTo("");
    setComposeSubject("");
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
      closeComposer();
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send email");
    } finally {
      setSending(false);
    }
  };

  const archiveSelectedThread = async () => {
    if (!selectedThreadId || archiving) return;
    setArchiving(true);
    setError(null);
    try {
      await archiveInboxThread(selectedThreadId);
      setRefreshTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive thread");
    } finally {
      setArchiving(false);
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
              <button
                onClick={archiveSelectedThread}
                disabled={!selectedThread || archiving}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs ring-1 ring-foreground/[0.08] disabled:opacity-40"
              >
                {archiving ? <Loader2 size={12} className="animate-spin" /> : <Archive size={12} />}
                Archive
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
                    <div className="min-w-0">
                      <p className="text-[11px] uppercase tracking-wide text-foreground/45">
                        From
                      </p>
                      <p className="truncate text-sm font-medium text-foreground">
                        {message.from_json?.name || message.from_json?.email || "Unknown sender"}
                      </p>
                      {message.from_json?.email && (
                        <p className="truncate text-xs font-mono text-foreground/65">
                          {message.from_json.email}
                        </p>
                      )}
                    </div>
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
                    <iframe
                      title={`email-preview-${message.gmail_message_id}`}
                      className="mt-3 w-full h-[560px] rounded-xl border border-foreground/[0.08] bg-white isolate"
                      sandbox="allow-popups allow-popups-to-escape-sandbox"
                      style={{ contain: "strict" }}
                      srcDoc={buildEmailHtmlDoc(message.subject, message.body_html_sanitized)}
                    />
                  ) : (
                    <p className="text-xs text-foreground/60 mt-3 whitespace-pre-wrap">
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
                                  attachmentActions[`${message.gmail_message_id}:${attachment.gmail_attachment_id}`] ===
                                    "downloading" ||
                                  attachmentActions[`${message.gmail_message_id}:${attachment.gmail_attachment_id}`] ===
                                    "saving"
                                }
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.06] disabled:opacity-50"
                              >
                                {attachmentActions[`${message.gmail_message_id}:${attachment.gmail_attachment_id}`] ===
                                "downloading" ? (
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
                                  attachmentActions[`${message.gmail_message_id}:${attachment.gmail_attachment_id}`] ===
                                    "downloading" ||
                                  attachmentActions[`${message.gmail_message_id}:${attachment.gmail_attachment_id}`] ===
                                    "saving"
                                }
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 ring-1 ring-foreground/[0.12] hover:bg-foreground/[0.06] disabled:opacity-50"
                              >
                                {attachmentActions[`${message.gmail_message_id}:${attachment.gmail_attachment_id}`] ===
                                "saving" ? (
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
                </article>
              ))
            )}

            {composerMode && (
              <article className="rounded-2xl ring-1 ring-blue-400/30 bg-card p-4">
                <h2 className="text-sm font-semibold text-foreground mb-3">
                  {composerMode === "new"
                    ? "New Email"
                    : composerMode === "reply"
                    ? "Reply in Thread"
                    : "Forward Message"}
                </h2>
                {(composerMode === "new" || composerMode === "forward") && (
                  <input
                    value={composeTo}
                    onChange={(e) => setComposeTo(e.target.value)}
                    placeholder="To"
                    className="w-full mb-2 rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
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
                  rows={6}
                  className="w-full rounded-xl bg-foreground/[0.05] px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-foreground/[0.2]"
                />
                <div className="flex justify-end gap-2 mt-4">
                  <button
                    onClick={closeComposer}
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
              </article>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
