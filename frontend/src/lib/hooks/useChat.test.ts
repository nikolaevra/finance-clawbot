import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Conversation } from "@/types";

const mocks = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  fetchConversation: vi.fn(),
  approveToolCalls: vi.fn(),
  loggerInfo: vi.fn(),
  loggerWarn: vi.fn(),
  loggerError: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  sendMessage: mocks.sendMessage,
  fetchConversation: mocks.fetchConversation,
  approveToolCalls: mocks.approveToolCalls,
}));

vi.mock("@/lib/logger", () => ({
  logger: {
    info: mocks.loggerInfo,
    warn: mocks.loggerWarn,
    error: mocks.loggerError,
  },
}));

import { useChat } from "./useChat";

function encode(chunk: string) {
  return new TextEncoder().encode(chunk);
}

function makeConversation(messages: Conversation["messages"] = []): Conversation {
  return {
    id: "conv-1",
    user_id: "user-1",
    title: "Chat",
    created_at: "2026-03-06T12:00:00.000Z",
    updated_at: "2026-03-06T12:00:00.000Z",
    messages,
  };
}

function makeResponse(
  reads: Array<Promise<{ done: boolean; value?: Uint8Array }> | { done: boolean; value?: Uint8Array }>
) {
  const read = vi.fn();
  reads.forEach((value) => read.mockImplementationOnce(() => Promise.resolve(value)));
  return {
    ok: true,
    body: {
      getReader: () => ({ read }),
    },
  };
}

describe("useChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchConversation.mockResolvedValue(makeConversation([]));
  });

  it("streams thinking/content/tool calls, updates title, and reloads messages", async () => {
    let resolveFinalRead: ((value: { done: boolean; value?: Uint8Array }) => void) | undefined;
    const pendingRead = new Promise<{ done: boolean; value?: Uint8Array }>((resolve) => {
      resolveFinalRead = resolve;
    });

    mocks.sendMessage.mockResolvedValue(
      makeResponse([
        {
          done: false,
          value: encode(
            'event: thinking\ndata: {"content":"Planning"}\n' +
              'event: content\ndata: {"content":"Hello"}\n' +
              'event: tool_call\ndata: {"index":0,"tool_call":{"id":"tool-1","type":"function","function":{"name":"memory_read","arguments":"{\\"date\\":\\"2026-03-05\\"}"}}}\n' +
              'event: title\ndata: {"title":"Daily recap"}\n' +
              "event: nonsense\ndata: {not json}\n"
          ),
        },
        pendingRead,
        { done: true },
      ])
    );

    const onTitleUpdate = vi.fn();
    const { result } = renderHook(() =>
      useChat({ conversationId: "conv-1", onTitleUpdate })
    );

    let sendPromise!: Promise<void>;
    await act(async () => {
      sendPromise = result.current.send("hi");
    });

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.streamingMessage?.thinking).toBe("Planning");
      expect(result.current.streamingMessage?.content).toBe("Hello");
      expect(result.current.streamingMessage?.toolCalls?.[0]?.id).toBe("tool-1");
    });

    expect(onTitleUpdate).toHaveBeenCalledWith("Daily recap");
    expect(mocks.loggerWarn).toHaveBeenCalledWith(
      "chat_stream_parse_error",
      expect.objectContaining({ eventType: "nonsense" })
    );

    mocks.fetchConversation.mockResolvedValue(
      makeConversation([
        {
          id: "assistant-1",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Hello",
          tool_calls: null,
          tool_call_id: null,
          model: "gpt-test",
          thinking: "Planning",
          sources: null,
          created_at: "2026-03-06T12:01:00.000Z",
        },
      ])
    );

    await act(async () => {
      resolveFinalRead?.({
        done: false,
        value: encode('event: done\ndata: {"content":"Hello"}\n'),
      });
      await sendPromise;
    });

    expect(result.current.streamingMessage).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.messages).toHaveLength(1);
    expect(mocks.fetchConversation).toHaveBeenCalledWith("conv-1");
  });

  it("handles approval pauses and resume flow", async () => {
    mocks.sendMessage.mockResolvedValue(
      makeResponse([
        {
          done: false,
          value: encode(
            'event: tool_approval_needed\ndata: {"conversation_id":"conv-1","tool_calls":[{"id":"tool-1","name":"accounting_create_bill","label":"Create bill","args":{"amount":10}}]}\n'
          ),
        },
        { done: true },
      ])
    );

    mocks.approveToolCalls.mockResolvedValue(
      makeResponse([
        {
          done: false,
          value: encode(
            'event: content\ndata: {"content":"Approved"}\n' +
              'event: done\ndata: {"content":"Approved"}\n'
          ),
        },
        { done: true },
      ])
    );

    const { result } = renderHook(() =>
      useChat({ conversationId: "conv-1" })
    );

    await act(async () => {
      await result.current.send("pay bill");
    });

    expect(result.current.pendingApproval?.toolCalls).toHaveLength(1);

    mocks.fetchConversation.mockResolvedValue(
      makeConversation([
        {
          id: "assistant-2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Approved",
          tool_calls: null,
          tool_call_id: null,
          model: "gpt-test",
          thinking: null,
          sources: null,
          created_at: "2026-03-06T12:02:00.000Z",
        },
      ])
    );

    await act(async () => {
      await result.current.resolveApproval(true);
    });

    expect(mocks.approveToolCalls).toHaveBeenCalledWith("conv-1", ["tool-1"], true);
    expect(result.current.pendingApproval).toBeNull();
    expect(result.current.messages[0]?.content).toBe("Approved");
  });
});
