import { createClient } from "./supabase";
import type {
  Conversation,
  MemoryListResponse,
  MemoryAccessLogEntry,
  UserDocument,
  Integration,
  AccountingTransaction,
  WorkflowTemplate,
  WorkflowRun,
  Skill,
  SkillContent,
  ToolCatalogEntry,
} from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5001";

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
  if (!res.ok) throw new Error("Failed to fetch conversations");
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
  message: string
): Promise<Response> {
  const headers = await getAuthHeaders();
  return fetch(`${API_URL}/api/chat/${conversationId}`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message }),
  });
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
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to upload document");
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

// ── Transaction API ─────────────────────────────────────────────────

export async function fetchTransactions(): Promise<AccountingTransaction[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/transactions`, { headers });
  if (!res.ok) throw new Error("Failed to fetch transactions");
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
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to create integration");
  }
  return res.json();
}

export async function syncIntegration(
  id: string
): Promise<{ status: string; accounts_synced: number; transactions_synced: number }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations/${id}/sync`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to sync integration");
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
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to connect Float");
  }
  return res.json();
}

export async function getGmailAuthUrl(): Promise<{ auth_url: string }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/integrations/gmail/auth-url`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to get Gmail auth URL");
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

// ── Workflow API ─────────────────────────────────────────────────────

export async function fetchWorkflowTemplates(): Promise<WorkflowTemplate[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflows`, { headers });
  if (!res.ok) throw new Error("Failed to fetch workflows");
  return res.json();
}

export async function fetchWorkflowTemplate(
  id: string
): Promise<WorkflowTemplate> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflows/${id}`, { headers });
  if (!res.ok) throw new Error("Failed to fetch workflow");
  return res.json();
}

export async function createWorkflowTemplate(
  data: Partial<WorkflowTemplate>
): Promise<WorkflowTemplate> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflows`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create workflow");
  return res.json();
}

export async function updateWorkflowTemplate(
  id: string,
  data: Partial<WorkflowTemplate>
): Promise<WorkflowTemplate> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflows/${id}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update workflow");
  return res.json();
}

export async function deleteWorkflowTemplate(id: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflows/${id}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error("Failed to delete workflow");
}

export async function triggerWorkflowRun(
  templateId: string,
  args?: Record<string, unknown>
): Promise<WorkflowRun> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflows/${templateId}/run`, {
    method: "POST",
    headers,
    body: JSON.stringify({ args }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to start workflow");
  }
  return res.json();
}

export async function fetchWorkflowRuns(
  status?: string
): Promise<WorkflowRun[]> {
  const headers = await getAuthHeaders();
  const url = new URL(`${API_URL}/api/workflow-runs`);
  if (status) url.searchParams.set("status", status);
  const res = await fetch(url.toString(), { headers });
  if (!res.ok) throw new Error("Failed to fetch workflow runs");
  return res.json();
}

export async function fetchWorkflowRun(id: string): Promise<WorkflowRun> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflow-runs/${id}`, { headers });
  if (!res.ok) throw new Error("Failed to fetch workflow run");
  return res.json();
}

export async function approveWorkflowRun(
  id: string,
  approve: boolean,
  comment?: string
): Promise<WorkflowRun> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflow-runs/${id}/approve`, {
    method: "POST",
    headers,
    body: JSON.stringify({ approve, comment }),
  });
  if (!res.ok) throw new Error("Failed to approve/reject workflow");
  return res.json();
}

export async function cancelWorkflowRun(id: string): Promise<WorkflowRun> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/workflow-runs/${id}/cancel`, {
    method: "POST",
    headers,
  });
  if (!res.ok) throw new Error("Failed to cancel workflow");
  return res.json();
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
  content: string
): Promise<Skill> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/skills`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name, content }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || "Failed to create skill");
  }
  return res.json();
}

export async function updateSkill(
  name: string,
  content: string
): Promise<Skill> {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${API_URL}/api/skills/${encodeURIComponent(name)}`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({ content }),
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
