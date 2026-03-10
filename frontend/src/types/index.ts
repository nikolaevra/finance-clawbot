export interface Conversation {
  id: string;
  user_id: string;
  title: string;
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

// ── Workflow types ──────────────────────────────────────────────────

export interface WorkflowStepDef {
  id: string;
  name: string;
  task?: string;
  args?: Record<string, unknown>;
  input_from?: string;
  timeout_seconds?: number;
  approval?: {
    required: boolean;
    prompt?: string;
  };
  condition?: string;
}

export interface WorkflowTemplate {
  id: string;
  user_id: string | null;
  name: string;
  description: string | null;
  steps: WorkflowStepDef[];
  schedule: string | null;
  is_active: boolean;
  created_at: string;
}

export interface WorkflowStepState {
  id: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped" | "awaiting_approval" | "approved";
  result: unknown;
  started_at: string | null;
  completed_at: string | null;
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
  type: string;
  actor: "gateway" | "lobster";
  timestamp: string;
  run_id?: string;
  step_id?: string;
  tool_name?: string;
  workflow_name?: string;
  message: string;
  detail?: string;
  preview?: { items: ApprovalPreviewItem[] };
}

export interface WorkflowRun {
  id: string;
  user_id: string;
  template_id: string;
  conversation_id: string | null;
  status: "pending" | "running" | "paused" | "completed" | "failed" | "cancelled";
  current_step_index: number;
  steps_state: WorkflowStepState[];
  resume_token: string | null;
  trigger: "manual" | "chat" | "scheduled";
  input_args: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  workflow_templates?: {
    name: string;
    description: string | null;
    steps?: WorkflowStepDef[];
  };
}

// ── Inbox types ─────────────────────────────────────────────────────

export type InboxTab = "inbox" | "unread" | "sent" | "drafts";

export interface EmailThread {
  gmail_thread_id: string;
  subject_normalized: string;
  participants_json: Array<{ name: string; email: string }>;
  last_message_internal_at: string | null;
  has_unread: boolean;
  snippet: string;
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
