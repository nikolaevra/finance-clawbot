import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Message, PendingToolApproval, SourceReference, ToolMeta } from "@/types";
import { makeMessage, makeSource, makeToolCall } from "@/test/test-utils";

vi.mock("./MessageBubble", () => ({
  default: ({
    message,
    toolMeta,
    displaySources,
  }: {
    message: Message;
    toolMeta?: ToolMeta;
    displaySources?: SourceReference[];
  }) => (
    <div data-testid={`bubble-${message.id}`}>
      <span>{message.role}</span>
      <span>{toolMeta?.name ?? "none"}</span>
      <span>{displaySources?.map((source) => source.source_file).join(",") ?? "no-sources"}</span>
    </div>
  ),
}));

vi.mock("./ToolApprovalCard", () => ({
  ToolApprovalCard: ({ approval }: { approval: PendingToolApproval }) => (
    <div data-testid="approval-card">{approval.toolCalls[0]?.name}</div>
  ),
}));

import MessageList, { dayKey, formatDayLabel } from "./MessageList";

describe("MessageList", () => {
  it("formats day keys and labels", () => {
    expect(dayKey("2026-03-06T18:40:00.000Z")).toBe("2026-03-06");
    expect(formatDayLabel(new Date())).toBe("Today");
  });

  it("reconstructs tool metadata and filters duplicate assistant citations", () => {
    const assistantWithToolCall = makeMessage({
      id: "assistant-tools",
      role: "assistant",
      content: null,
      tool_calls: [
        makeToolCall({
          id: "tool-call-1",
          function: {
            name: "memory_search",
            arguments: JSON.stringify({ query: "budget" }),
          },
        }),
      ],
    });

    const toolMessage = makeMessage({
      id: "tool-message",
      role: "tool",
      tool_call_id: "tool-call-1",
      content: JSON.stringify({
        results: [
          { source_file: "daily/2026-03-05.md" },
          { source_file: "documents/report.pdf" },
        ],
      }),
    });

    const assistantReply = makeMessage({
      id: "assistant-reply",
      role: "assistant",
      content: "Here you go",
      sources: [
        makeSource({ source_file: "daily/2026-03-05.md" }),
        makeSource({ source_file: "external/report" }),
      ],
    });

    render(
      <MessageList
        messages={[assistantWithToolCall, toolMessage, assistantReply]}
        streamingMessage={null}
      />
    );

    expect(screen.queryByTestId("bubble-assistant-tools")).not.toBeInTheDocument();
    expect(screen.getByTestId("bubble-tool-message")).toHaveTextContent("memory_search");
    expect(screen.getByTestId("bubble-assistant-reply")).toHaveTextContent("external/report");
    expect(screen.getByText("Today")).toBeInTheDocument();
  });

  it("renders pending approval cards", () => {
    render(
      <MessageList
        messages={[makeMessage({ id: "user-1", role: "user", content: "hi" })]}
        streamingMessage={null}
        pendingApproval={{
          conversationId: "conv-1",
          toolCalls: [
            {
              id: "tool-1",
              name: "accounting_create_bill",
              label: "Create Bill",
              args: { amount: 100 },
            },
          ],
        }}
        onResolveApproval={vi.fn()}
      />
    );

    expect(screen.getByTestId("approval-card")).toHaveTextContent(
      "accounting_create_bill"
    );
  });
});
