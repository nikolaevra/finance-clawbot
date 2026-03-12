export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  conversation_type?: "live" | "background";
  agent_mode?: "live" | "background";
  agent_source?: string | null;
  agent_run_id?: string | null;
  agent_name?: string | null;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}

export interface SourceReference {
  source_file: string;
  score: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string | null;
  tool_calls: ToolCall[] | null;
  tool_call_id: string | null;
  model: string | null;
  thinking: string | null;
  sources: SourceReference[] | null;
  created_at: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

/** Metadata about a tool call, resolved from the preceding assistant message. */
export interface ToolMeta {
  name: string;
  args: Record<string, unknown>;
}

export interface PendingToolApproval {
  conversationId: string;
  toolCalls: Array<{
    id: string;
    name: string;
    label: string;
    args: Record<string, unknown>;
  }>;
}

export interface StreamingMessage {
  role: "assistant";
  content: string;
  thinking: string;
  toolCalls: ToolCall[] | null;
  sources: SourceReference[] | null;
  isStreaming: boolean;
  pendingApproval: PendingToolApproval | null;
}

// ── Memory types ─────────────────────────────────────────────────────

export interface MemoryFile {
  date: string;
  source_file: string;
  access_count: number;
}

export interface MemoryListResponse {
  daily: MemoryFile[];
  long_term: {
    source_file: string;
    exists: boolean;
    access_count: number;
  };
}

export interface MemoryAccessLogEntry {
  id: string;
  conversation_id: string;
  conversation_title: string;
  tool_name: string;
  created_at: string;
}

// ── Document types ──────────────────────────────────────────────────

export interface UserDocument {
  id: string;
  user_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  storage_path: string;
  status: "processing" | "ready" | "error";
  created_at: string;
}

// ── Integration types ───────────────────────────────────────────────

export type IntegrationProvider = "quickbooks" | "netsuite" | "gmail" | "float";

export interface Integration {
  id: string;
  user_id: string;
  provider: IntegrationProvider;
  integration_name: string;
  status: "active" | "error" | "disconnected";
  created_at: string;
  updated_at: string;
}

// ── Skill types ─────────────────────────────────────────────────────

export interface Skill {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  schedule_enabled?: boolean;
  schedule_type?: "daily" | "weekly" | null;
  schedule_days?: number[] | null;
  schedule_time?: string | null;
  schedule_timezone?: string | null;
  trigger_enabled?: boolean;
  trigger_provider?: "gmail" | null;
  trigger_event?: "new_email" | null;
  trigger_filters?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SkillContent {
  name: string;
  content: string;
  enabled?: boolean;
  schedule_enabled?: boolean;
  schedule_type?: "daily" | "weekly" | null;
  schedule_days?: number[] | null;
  schedule_time?: string | null;
  schedule_timezone?: string | null;
  trigger_enabled?: boolean;
  trigger_provider?: "gmail" | null;
  trigger_event?: "new_email" | null;
  trigger_filters?: Record<string, unknown> | null;
}

export interface ToolCatalogEntry {
  name: string;
  label: string;
  description: string;
  category: string;
  requires_approval: boolean;
}

// ── Activity types ─────────────────────────────────────────────────

export interface ApprovalPreviewItem {
  step: string;
  summary?: string;
  type?: "suggestions" | "anomalies" | "report";
  count?: number;
  sample?: Array<Record<string, unknown>>;
  preview?: string;
}

export interface ActivityEvent {
  id?: string;
  type: string;
  actor: "agent";
  timestamp: string;
  source?: string;
  status?: string;
  conversation_id?: string;
  run_id?: string;
  step_id?: string;
  tool_name?: string;
  workflow_name?: string;
  message: string;
  detail?: string;
  preview?: { items: ApprovalPreviewItem[] };
  payload?: unknown;
  simulated_thinking?: string;
  verbose_data?: Record<string, unknown>;
}

// ── Inbox types ─────────────────────────────────────────────────────

export type InboxTab = "inbox" | "all_mail" | "skip_inbox" | "unread" | "sent" | "drafts";

export interface EmailThread {
  gmail_thread_id: string;
  subject_normalized: string;
  participants_json: Array<{ name: string; email: string }>;
  last_message_internal_at: string | null;
  has_unread: boolean;
  snippet: string;
  ai_summary_preview: string;
}

export interface EmailMessage {
  id: string;
  gmail_message_id: string;
  gmail_thread_id: string;
  subject: string;
  snippet: string;
  body_text: string;
  body_html_sanitized: string;
  internal_date_ts: number | null;
  from_json: { name: string; email: string };
  to_json: Array<{ name: string; email: string }>;
  cc_json: Array<{ name: string; email: string }>;
  bcc_json: Array<{ name: string; email: string }>;
  is_read: boolean;
  is_sent: boolean;
  is_draft: boolean;
  label_ids_json: string[];
}

export interface EmailAttachment {
  gmail_message_id: string;
  gmail_attachment_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  storage_key: string | null;
}
