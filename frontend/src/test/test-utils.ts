import type {
  ActivityEvent,
  Integration,
  MemoryListResponse,
  Message,
  SourceReference,
  ToolCall,
  ToolCatalogEntry,
  UserDocument,
} from "@/types";

export function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    conversation_id: "conv-1",
    role: "assistant",
    content: "Hello",
    tool_calls: null,
    tool_call_id: null,
    model: "gpt-test",
    thinking: null,
    sources: null,
    created_at: "2026-03-06T12:00:00.000Z",
    ...overrides,
  };
}

export function makeToolCall(
  overrides: Partial<ToolCall> & {
    function?: Partial<ToolCall["function"]>;
  } = {}
): ToolCall {
  return {
    id: "tool-1",
    type: "function",
    function: {
      name: "memory_read",
      arguments: JSON.stringify({ date: "2026-03-05" }),
      ...overrides.function,
    },
    ...overrides,
  };
}

export function makeSource(
  overrides: Partial<SourceReference> = {}
): SourceReference {
  return {
    source_file: "daily/2026-03-05.md",
    score: 0.91,
    ...overrides,
  };
}

export function makeActivityEvent(
  overrides: Partial<ActivityEvent> = {}
): ActivityEvent {
  return {
    type: "message_received",
    actor: "agent",
    timestamp: "2026-03-06T12:00:00.000Z",
    message: "Processing message",
    ...overrides,
  };
}

export function makeIntegration(
  overrides: Partial<Integration> = {}
): Integration {
  return {
    id: "integration-1",
    user_id: "user-1",
    provider: "quickbooks",
    integration_name: "QuickBooks Online",
    status: "active",
    created_at: "2026-03-06T12:00:00.000Z",
    updated_at: "2026-03-06T12:00:00.000Z",
    ...overrides,
  };
}

export function makeDocument(
  overrides: Partial<UserDocument> = {}
): UserDocument {
  return {
    id: "doc-1",
    user_id: "user-1",
    filename: "report.pdf",
    file_type: "pdf",
    file_size: 1024,
    storage_path: "user-1/documents/report.pdf",
    status: "ready",
    created_at: "2026-03-06T12:00:00.000Z",
    ...overrides,
  };
}

export function makeToolCatalogEntry(
  overrides: Partial<ToolCatalogEntry> = {}
): ToolCatalogEntry {
  return {
    name: "memory_read",
    label: "Memory Read",
    description: "Read memory files",
    category: "memory",
    requires_approval: false,
    ...overrides,
  };
}

export function makeMemories(
  overrides: Partial<MemoryListResponse> = {}
): MemoryListResponse {
  return {
    daily: [
      {
        date: "2026-03-06",
        source_file: "daily/2026-03-06.md",
        access_count: 2,
      },
    ],
    long_term: {
      source_file: "MEMORY.md",
      exists: true,
      access_count: 1,
    },
    ...overrides,
  };
}

export function createEventStreamResponse(events: Array<[string, unknown]>): Response {
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= events.length) {
        controller.close();
        return;
      }

      const [event, data] = events[index++];
      const chunk = `event: ${event}\ndata: ${JSON.stringify(data)}\n`;
      controller.enqueue(new TextEncoder().encode(chunk));
    },
  });

  return new Response(stream);
}
