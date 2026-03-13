import { createClient } from "./supabase";
import type {
  Conversation,
  MemoryListResponse,
  MemoryAccessLogEntry,
  UserDocument,
  Integration,
  Skill,
  SkillContent,
  ToolCatalogEntry,
  InboxTab,
  EmailThread,
  EmailMessage,
  EmailAttachment,
} from "@/types";
import { logger } from "./logger";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5001";

async function readErrorBody(res: Response): Promise<string | undefined> {
  try {
    const body = await res.json();
    return body?.error || JSON.stringify(body).slice(0, 200);
  } catch {
    return undefined;
  }
}

async function logApiFailure(
  endpoint: string,
  method: string,
  res: Response
): Promise<void> {
  const requestId = res.headers.get("X-Request-ID") || undefined;
  const errorBody = await readErrorBody(res);
  logger.warn("api_request_failed", {
    endpoint,
    method,
    status: res.status,
    requestId,
    errorBody,
  });
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error("Not authenticated");
  }

  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

export async function fetchConversations(): Promise<Conversation[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/conversations`, { headers });
  if (!res.ok) {
    await logApiFailure("/api/conversations", "GET", res);
    throw new Error("Failed to fetch conversations");
  }
  return res.json();
}

export async function fetchCurrentConversation(): Promise<Conversation> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/conversations/current`, { headers });
  if (!res.ok) throw new Error("Failed to fetch conversation");
  return res.json();
}

export async function createConversation(
  title?: string
): Promise<Conversation> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/conversations`, {
    method: "POST",
    headers,
    body: JSON.stringify({ title: title || "New Chat" }),
  });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function fetchConversation(id: string): Promise<Conversation> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/conversations/${id}`, { headers });
  if (!res.ok) throw new Error("Failed to fetch conversation");
  return res.json();
}

export async function updateConversation(
  id: string,
  data: { title?: string }
): Promise<Conversation> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/conversations/${id}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update conversation");
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/conversations/${id}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function sendMessage(
  conversationId: string,
  message: string,
  forcedSkill?: string
): Promise<Response> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/chat/${conversationId}`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, forced_skill: forcedSkill }),
  });
  if (!res.ok) {
    await logApiFailure(`/api/chat/${conversationId}`, "POST", res);
  }
  return res;
}

// ── Tool Approval API ────────────────────────────────────────────────

export async function approveToolCalls(
  conversationId: string,
  toolCallIds: string[],
  approved: boolean
): Promise<Response> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/chat/${conversationId}/approve-tools`, {
    method: "POST",
    headers,
    body: JSON.stringify({ tool_call_ids: toolCallIds, approved }),
  });
  if (!res.ok) {
    await logApiFailure(`/api/chat/${conversationId}/approve-tools`, "POST", res);
  }
  return res;
}

// ── Bootstrap File API ──────────────────────────────────────────────

export async function fetchBootstrapFile(
  filename: string
): Promise<{ filename: string; content: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/memories/bootstrap/${encodeURIComponent(filename)}`,
    { headers }
  );
  if (!res.ok) throw new Error(`Failed to fetch ${filename}`);
  return res.json();
}

export async function updateBootstrapFile(
  filename: string,
  content: string
): Promise<{ filename: string; content: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/memories/bootstrap/${encodeURIComponent(filename)}`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({ content }),
    }
  );
  if (!res.ok) throw new Error(`Failed to update ${filename}`);
  return res.json();
}

// ── Memory API ───────────────────────────────────────────────────────

export async function fetchMemories(): Promise<MemoryListResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/memories`, { headers });
  if (!res.ok) throw new Error("Failed to fetch memories");
  return res.json();
}

export async function fetchDailyLog(
  date: string
): Promise<{ date: string; source_file: string; content: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/memories/daily/${date}`, {
    headers,
  });
  if (!res.ok) throw new Error("Failed to fetch daily log");
  return res.json();
}

export async function updateDailyLog(
  date: string,
  content: string
): Promise<{ date: string; source_file: string; content: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/memories/daily/${date}`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to update daily log");
  return res.json();
}

export async function fetchLongTermMemory(): Promise<{
  source_file: string;
  content: string;
}> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/memories/long-term`, { headers });
  if (!res.ok) throw new Error("Failed to fetch long-term memory");
  return res.json();
}

export async function updateLongTermMemory(
  content: string
): Promise<{ source_file: string; content: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/memories/long-term`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to update long-term memory");
  return res.json();
}

export async function fetchMemoryAccessLog(
  sourceFile: string
): Promise<MemoryAccessLogEntry[]> {
  const headers = await getAuthHeaders();
  // sourceFile contains slashes (e.g. "daily/2025-02-08.md") which must
  // be preserved for the Flask <path:source_file> converter.
  const encoded = sourceFile
    .split("/")
    .map((s) => encodeURIComponent(s))
    .join("/");
  const res = await fetch(
    `${API_URL}/api/memories/access-log/${encoded}`,
    { headers }
  );
  if (!res.ok) throw new Error("Failed to fetch memory access log");
  return res.json();
}

// ── Document API ────────────────────────────────────────────────────

export async function fetchDocuments(): Promise<UserDocument[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/documents`, { headers });
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

export async function uploadDocument(file: File): Promise<UserDocument> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) throw new Error("Not authenticated");

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/documents/upload`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${session.access_token}`,
    },
    body: formData,
  });
  if (!res.ok) {
    await logApiFailure("/api/documents/upload", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to upload document");
  }
  return res.json();
}

function extractGoogleDriveFileId(input: string): string {
  const raw = input.trim();
  if (!raw) return "";
  if (/^[a-zA-Z0-9_-]{20,}$/.test(raw)) return raw;
  try {
    const url = new URL(raw);
    const fileMatch = url.pathname.match(/\/file\/d\/([a-zA-Z0-9_-]+)/);
    if (fileMatch?.[1]) return fileMatch[1];
    const idParam = url.searchParams.get("id");
    if (idParam) return idParam;
  } catch {
    // ignore parse errors and return as-is for backend validation
  }
  return raw;
}

export async function linkGoogleDriveDocument(
  fileIdOrUrl: string
): Promise<UserDocument> {
  const headers = await getAuthHeaders();
  const fileId = extractGoogleDriveFileId(fileIdOrUrl);
  if (!fileId) {
    throw new Error("Google Drive file URL or file ID is required");
  }
  const endpoint = "/api/documents/link-google-drive";
  const res = await fetch(`${API_URL}${endpoint}`, {
    method: "POST",
    headers,
    body: JSON.stringify({ file_id: fileId }),
  });
  if (!res.ok) {
    await logApiFailure(endpoint, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to link Google Drive file");
  }
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/documents/${id}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error("Failed to delete document");
}

export async function fetchDocumentContent(
  id: string
): Promise<{ id: string; filename: string; content: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/documents/${id}/content`, {
    headers,
  });
  if (!res.ok) throw new Error("Failed to fetch document content");
  return res.json();
}

// ── Integration API ──────────────────────────────────────────────────

export async function fetchIntegrations(): Promise<Integration[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations`, { headers });
  if (!res.ok) throw new Error("Failed to fetch integrations");
  return res.json();
}

export async function createLinkToken(
  organizationName?: string,
  email?: string,
  integrationSlug?: string
): Promise<{ link_token: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations/link-token`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      organization_name: organizationName,
      email,
      integration_slug: integrationSlug,
    }),
  });
  if (!res.ok) {
    await logApiFailure("/api/integrations/link-token", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to create link token");
  }
  return res.json();
}

export async function createIntegration(
  publicToken: string,
  provider: string = "quickbooks",
  integrationName: string = "QuickBooks Online"
): Promise<Integration> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      public_token: publicToken,
      provider,
      integration_name: integrationName,
    }),
  });
  if (!res.ok) {
    await logApiFailure("/api/integrations", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to create integration");
  }
  return res.json();
}

export async function deleteIntegration(id: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations/${id}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error("Failed to disconnect integration");
}

export async function connectFloat(apiToken: string): Promise<Integration> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations/float`, {
    method: "POST",
    headers,
    body: JSON.stringify({ api_token: apiToken }),
  });
  if (!res.ok) {
    await logApiFailure("/api/integrations/float", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to connect Float");
  }
  return res.json();
}

export async function getGmailAuthUrl(
  provider: "gmail" | "google_workspace" = "gmail"
): Promise<{ auth_url: string }> {
  const headers = await getAuthHeaders();
  const endpoint =
    provider === "google_workspace"
      ? "/api/integrations/google-workspace/auth-url"
      : "/api/integrations/gmail/auth-url";
  const res = await fetch(`${API_URL}${endpoint}`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    await logApiFailure(endpoint, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(
      body.error ||
        (provider === "google_workspace"
          ? "Failed to get Google Workspace auth URL"
          : "Failed to get Gmail auth URL")
    );
  }
  return res.json();
}

// ── Inbox API ───────────────────────────────────────────────────────

export async function fetchInboxThreads(
  tab: InboxTab = "inbox",
  page: number = 1,
  limit: number = 25
): Promise<{ threads: EmailThread[]; page: number; limit: number; has_more: boolean }> {
  const headers = await getAuthHeaders();
  const url = new URL(`${API_URL}/api/inbox/threads`);
  url.searchParams.set("tab", tab);
  url.searchParams.set("page", String(page));
  url.searchParams.set("limit", String(limit));
  const res = await fetch(url.toString(), { headers });
  if (!res.ok) {
    await logApiFailure("/api/inbox/threads", "GET", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to fetch inbox threads");
  }
  return res.json();
}

export async function fetchInboxThread(
  threadId: string
): Promise<{
  thread: EmailThread;
  messages: EmailMessage[];
  attachments_by_message: Record<string, EmailAttachment[]>;
  hydrate_enqueued: boolean;
}> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/inbox/threads/${encodeURIComponent(threadId)}`, { headers });
  if (!res.ok) {
    await logApiFailure(`/api/inbox/threads/${threadId}`, "GET", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to fetch thread");
  }
  return res.json();
}

export async function sendInboxEmail(payload: {
  to: string;
  subject: string;
  body: string;
  cc?: string;
}): Promise<{ id: string; threadId: string; labelIds: string[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/inbox/send`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    await logApiFailure("/api/inbox/send", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to send email");
  }
  return res.json();
}

export async function replyInboxEmail(payload: {
  message_id: string;
  body: string;
  cc?: string;
}): Promise<{ id: string; threadId: string; labelIds: string[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/inbox/reply`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    await logApiFailure("/api/inbox/reply", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to send reply");
  }
  return res.json();
}

export async function forwardInboxEmail(payload: {
  message_id: string;
  to: string;
  body?: string;
  cc?: string;
}): Promise<{ id: string; threadId: string; labelIds: string[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/inbox/forward`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    await logApiFailure("/api/inbox/forward", "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to forward email");
  }
  return res.json();
}

export async function sendInboxDraft(
  messageId: string
): Promise<{ id: string; threadId: string; labelIds: string[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/inbox/drafts/${encodeURIComponent(messageId)}/send`,
    {
      method: "POST",
      headers,
    }
  );
  if (!res.ok) {
    await logApiFailure(`/api/inbox/drafts/${messageId}/send`, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to send draft");
  }
  return res.json();
}

export async function updateInboxDraft(
  messageId: string,
  body: string
): Promise<{ id: string; message_id: string; threadId: string; labelIds: string[] }> {
  const headers = await getAuthHeaders();
  const endpoint = `/api/inbox/drafts/${encodeURIComponent(messageId)}`;
  const res = await fetch(`${API_URL}${endpoint}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ body }),
  });
  if (!res.ok) {
    await logApiFailure(endpoint, "PATCH", res);
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.error || "Failed to update draft");
  }
  return res.json();
}

export async function markInboxMessageRead(
  messageId: string
): Promise<{ status: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/inbox/messages/${encodeURIComponent(messageId)}/read`,
    {
      method: "POST",
      headers,
    }
  );
  if (!res.ok) {
    await logApiFailure(`/api/inbox/messages/${messageId}/read`, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to mark message read");
  }
  return res.json();
}

export async function archiveInboxThread(
  threadId: string
): Promise<{ status: string; archived_messages: number }> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/inbox/threads/${encodeURIComponent(threadId)}/archive`,
    {
      method: "POST",
      headers,
    }
  );
  if (!res.ok) {
    await logApiFailure(`/api/inbox/threads/${threadId}/archive`, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to archive thread");
  }
  return res.json();
}

export async function discardInboxThreadDrafts(
  threadId: string
): Promise<{ status: string; discarded_drafts: number }> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/inbox/threads/${encodeURIComponent(threadId)}/discard`,
    {
      method: "POST",
      headers,
    }
  );
  if (!res.ok) {
    await logApiFailure(`/api/inbox/threads/${threadId}/discard`, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to discard draft thread");
  }
  return res.json();
}

export async function downloadInboxAttachment(
  messageId: string,
  attachmentId: string
): Promise<{ blob: Blob; filename: string }> {
  const headers = await getAuthHeaders();
  const endpoint = `/api/inbox/messages/${encodeURIComponent(messageId)}/attachments/${encodeURIComponent(attachmentId)}/download`;
  const res = await fetch(`${API_URL}${endpoint}`, {
    headers,
  });
  if (!res.ok) {
    await logApiFailure(endpoint, "GET", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to download attachment");
  }

  const contentDisposition = res.headers.get("content-disposition") || "";
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  const asciiMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  const filename = utf8Match?.[1]
    ? decodeURIComponent(utf8Match[1])
    : (asciiMatch?.[1] || "attachment");

  const blob = await res.blob();
  return { blob, filename };
}

export async function saveInboxAttachmentToDocuments(
  messageId: string,
  attachmentId: string
): Promise<UserDocument> {
  const headers = await getAuthHeaders();
  const endpoint = `/api/inbox/messages/${encodeURIComponent(messageId)}/attachments/${encodeURIComponent(attachmentId)}/save-to-documents`;
  const res = await fetch(`${API_URL}${endpoint}`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    await logApiFailure(endpoint, "POST", res);
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to save attachment");
  }
  return res.json();
}

// ── Activity SSE ────────────────────────────────────────────────────

export function getActivityStreamUrl(token: string): string {
  return `${API_URL}/api/activity/events?token=${encodeURIComponent(token)}`;
}

export async function getAuthToken(): Promise<string> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new Error("Not authenticated");
  }
  return session.access_token;
}

// ── Skills API ──────────────────────────────────────────────────────

export async function fetchSkills(): Promise<Skill[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/skills`, { headers });
  if (!res.ok) throw new Error("Failed to fetch skills");
  return res.json();
}

export async function fetchSkill(name: string): Promise<SkillContent> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/skills/${encodeURIComponent(name)}`,
    { headers }
  );
  if (!res.ok) throw new Error("Failed to fetch skill");
  return res.json();
}

export async function createSkill(
  name: string,
  content: string,
  automation?: Partial<Skill>
): Promise<Skill> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/skills`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name, content, ...automation }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to create skill");
  }
  return res.json();
}

export async function updateSkill(
  name: string,
  content: string,
  automation?: Partial<Skill>,
  newName?: string
): Promise<Skill> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/skills/${encodeURIComponent(name)}`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({ content, ...automation, new_name: newName }),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to update skill");
  }
  return res.json();
}

export async function deleteSkill(name: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/skills/${encodeURIComponent(name)}`,
    {
      method: "DELETE",
      headers,
    }
  );
  if (!res.ok) throw new Error("Failed to delete skill");
}

export async function toggleSkill(
  name: string,
  enabled: boolean
): Promise<Skill> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/skills/${encodeURIComponent(name)}/toggle`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ enabled }),
    }
  );
  if (!res.ok) throw new Error("Failed to toggle skill");
  return res.json();
}

// ── Tool Catalog API ────────────────────────────────────────────────

export async function fetchToolCatalog(): Promise<ToolCatalogEntry[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/tools`, { headers });
  if (!res.ok) throw new Error("Failed to fetch tool catalog");
  return res.json();
}
