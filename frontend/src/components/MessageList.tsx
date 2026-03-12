"use client";

import { useEffect, useLayoutEffect, useRef, useMemo, Fragment } from "react";
import type { Message, StreamingMessage, ToolMeta, SourceReference, PendingToolApproval } from "@/types";
import MessageBubble from "./MessageBubble";
import { ToolApprovalCard } from "./ToolApprovalCard";

interface MessageListProps {
  messages: Message[];
  streamingMessage: StreamingMessage | null;
  pendingApproval?: PendingToolApproval | null;
  onResolveApproval?: (approved: boolean) => void;
  conversationId?: string | null;
  onPasteMessageBody?: (body: string) => void;
}

export function formatDayLabel(date: Date): string {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msgDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.floor(
    (today.getTime() - msgDay.getTime()) / 86400000
  );

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function dayKey(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function DaySeparator({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-4 py-6 px-4">
      <div className="h-px flex-1 bg-foreground/[0.06]" />
      <span className="text-[11px] font-medium text-foreground/20 tracking-wide">
        {label}
      </span>
      <div className="h-px flex-1 bg-foreground/[0.06]" />
    </div>
  );
}

export default function MessageList({
  messages,
  streamingMessage,
  pendingApproval,
  onResolveApproval,
  conversationId,
  onPasteMessageBody,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevConversationId = useRef<string | null | undefined>(undefined);

  // Scroll to bottom instantly whenever the conversation changes
  useLayoutEffect(() => {
    if (conversationId !== prevConversationId.current) {
      prevConversationId.current = conversationId;
      bottomRef.current?.scrollIntoView();
    }
  }, [conversationId, messages]);

  // Auto-scroll on new streaming content when already near the bottom
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      150;

    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streamingMessage?.content, streamingMessage?.thinking]);

  const { toolCallMap, toolSourceFiles } = useMemo(() => {
    const map = new Map<string, ToolMeta>();
    const sourceFiles = new Set<string>();

    for (const msg of messages) {
      if (msg.role === "assistant" && msg.tool_calls) {
        for (const tc of msg.tool_calls) {
          let args: Record<string, unknown> = {};
          try {
            args =
              typeof tc.function.arguments === "string"
                ? JSON.parse(tc.function.arguments)
                : tc.function.arguments;
          } catch {
            /* ignore parse errors */
          }
          map.set(tc.id, { name: tc.function.name, args });

          if (tc.function.name === "document_read" && args.filename) {
            sourceFiles.add(`documents/${args.filename}`);
          } else if (tc.function.name === "memory_read") {
            const d = args.date as string | undefined;
            if (d) {
              sourceFiles.add(`daily/${d}.md`);
            } else {
              sourceFiles.add(
                `daily/${new Date().toISOString().split("T")[0]}.md`
              );
            }
          }
        }
      }
    }

    for (const msg of messages) {
      if (msg.role === "tool" && msg.tool_call_id && msg.content) {
        const meta = map.get(msg.tool_call_id);
        if (meta?.name === "memory_search") {
          try {
            const data = JSON.parse(msg.content);
            for (const r of data.results ?? []) {
              if (r.source_file) sourceFiles.add(r.source_file);
            }
          } catch {
            /* ignore */
          }
        }
      }
    }

    return { toolCallMap: map, toolSourceFiles: sourceFiles };
  }, [messages]);

  if (messages.length === 0 && !streamingMessage) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center space-y-3">
          <div className="mx-auto w-12 h-12 rounded-2xl bg-foreground/[0.06] flex items-center justify-center">
            <span className="text-xl">✦</span>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground/80 tracking-tight">
              Finance Assistant
            </h2>
            <p className="mt-1 text-sm text-foreground/30">
              How can I help you today?
            </p>
          </div>
        </div>
      </div>
    );
  }

  let lastDay = "";

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl py-4">
        {messages.map((msg) => {
          if (
            msg.role === "assistant" &&
            !msg.content &&
            msg.tool_calls &&
            msg.tool_calls.length > 0
          ) {
            return null;
          }

          if (
            msg.role !== "tool" &&
            msg.role !== "user" &&
            !msg.content
          ) {
            return null;
          }

          const currentDay = dayKey(msg.created_at);
          const showSeparator = currentDay !== lastDay;
          lastDay = currentDay;

          const toolMeta =
            msg.role === "tool" && msg.tool_call_id
              ? toolCallMap.get(msg.tool_call_id)
              : undefined;

          let displaySources: SourceReference[] | undefined;
          if (msg.role === "assistant" && msg.sources && msg.sources.length > 0) {
            const filtered = msg.sources.filter(
              (s) => !toolSourceFiles.has(s.source_file)
            );
            displaySources = filtered;
          }

          return (
            <Fragment key={msg.id}>
              {showSeparator && (
                <DaySeparator
                  label={formatDayLabel(new Date(msg.created_at))}
                />
              )}
              <MessageBubble
                message={msg}
                toolMeta={toolMeta}
                displaySources={displaySources}
                onPasteBody={onPasteMessageBody}
              />
            </Fragment>
          );
        })}
        {streamingMessage && (
          <MessageBubble message={streamingMessage} onPasteBody={onPasteMessageBody} />
        )}
        {pendingApproval && onResolveApproval && (
          <ToolApprovalCard
            approval={pendingApproval}
            onResolve={onResolveApproval}
          />
        )}
        <div ref={bottomRef} className="h-6" />
      </div>
    </div>
  );
}
