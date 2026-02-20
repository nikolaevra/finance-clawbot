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

export interface StreamingMessage {
  role: "assistant";
  content: string;
  thinking: string;
  toolCalls: ToolCall[] | null;
  sources: SourceReference[] | null;
  isStreaming: boolean;
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

export interface Integration {
  id: string;
  user_id: string;
  provider: string;
  integration_name: string;
  status: "active" | "syncing" | "error" | "disconnected";
  last_sync_at: string | null;
  last_sync_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountingAccount {
  id: string;
  name: string;
  description: string | null;
  classification: string | null;
  type: string | null;
  current_balance: number | null;
  currency: string;
  status: string | null;
}

export interface AccountingTransaction {
  id: string;
  remote_id: string;
  transaction_date: string | null;
  number: string | null;
  memo: string | null;
  total_amount: number | null;
  currency: string;
  contact_name: string | null;
  account_name: string | null;
  transaction_type: string | null;
  provider: string | null;
  integration_name: string | null;
  remote_created_at: string | null;
  remote_updated_at: string | null;
  created_at: string;
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
