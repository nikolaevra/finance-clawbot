"use client";

import { useEffect, useRef, useMemo, Fragment } from "react";
import type { Message, StreamingMessage, ToolMeta, SourceReference } from "@/types";
import MessageBubble from "./MessageBubble";

interface MessageListProps {
  messages: Message[];
  streamingMessage: StreamingMessage | null;
}

/** Return a human-friendly label for a calendar day. */
function formatDayLabel(date: Date): string {
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

/** Get the calendar-day key (YYYY-MM-DD) for a message timestamp. */
function dayKey(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function DaySeparator({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-4 px-4">
      <div className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
      <span className="text-xs font-medium text-zinc-500 whitespace-nowrap">
        {label}
      </span>
      <div className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
    </div>
  );
}

export default function MessageList({
  messages,
  streamingMessage,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when new content arrives
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Only auto-scroll if user is near the bottom
    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      150;

    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streamingMessage?.content, streamingMessage?.thinking]);

  // ── Tool-call metadata resolution ─────────────────────────────
  // Build a map of tool_call_id → {name, args} so tool-result messages
  // can be rendered as compact citation cards instead of raw text dumps.
  // Also track which source_files are already covered by tool calls so
  // the SourcesCitation on the final assistant message doesn't duplicate.
  //
  // NOTE: This hook MUST be called before the early return below so
  // that the number / order of hooks is stable across renders.

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

          // Track source files covered by document/memory tools
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
          } else if (tc.function.name === "memory_search") {
            // memory_search sources are extracted from the result, not args.
            // We'll resolve them from the matching tool message below.
          }
        }
      }
    }

    // Second pass: resolve memory_search sources from tool result content
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

  // Empty-state: show welcome screen
  if (messages.length === 0 && !streamingMessage) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-semibold text-zinc-800 dark:text-zinc-200">
            Finance Assistant
          </h2>
          <p className="mt-2 text-zinc-500 dark:text-zinc-500">
            How can I help you today?
          </p>
        </div>
      </div>
    );
  }

  // Build list with day separators inserted between date boundaries
  let lastDay = "";

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl">
        {messages.map((msg) => {
          // Skip assistant messages that carry only tool_calls with no visible content
          if (
            msg.role === "assistant" &&
            !msg.content &&
            msg.tool_calls &&
            msg.tool_calls.length > 0
          ) {
            return null;
          }

          // Skip any non-tool message with no content at all (system, empty assistant, etc.)
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

          // Resolve tool metadata for tool-result messages
          const toolMeta =
            msg.role === "tool" && msg.tool_call_id
              ? toolCallMap.get(msg.tool_call_id)
              : undefined;

          // For assistant messages with sources, filter out sources
          // that are already shown as tool-result citation cards
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
              />
            </Fragment>
          );
        })}
        {streamingMessage && <MessageBubble message={streamingMessage} />}
        <div ref={bottomRef} className="h-4" />
      </div>
    </div>
  );
}
