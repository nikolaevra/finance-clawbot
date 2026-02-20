"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, User, Bot, Wrench, ExternalLink } from "lucide-react";
import { useState } from "react";
import Link from "next/link";
import type { Message, StreamingMessage, ToolMeta, SourceReference } from "@/types";
import ThinkingIndicator from "./ThinkingIndicator";
import { WorkflowApprovalCard, WorkflowStatusBadge } from "./WorkflowApproval";
import SourcesCitation, {
  sourceLabel,
  sourceHref,
  SourceIcon,
  typeLabel,
  typeBadgeClasses,
} from "./SourcesCitation";

/** Tool names whose results should render as compact citation cards. */
const DOCUMENT_TOOLS = new Set([
  "document_read",
  "document_list",
  "memory_read",
  "memory_search",
]);

const WORKFLOW_TOOLS = new Set([
  "workflow_run",
  "workflow_status",
  "workflow_approve",
  "workflow_list",
]);

interface MessageBubbleProps {
  message: Message | StreamingMessage;
  /** Resolved tool metadata (name + parsed args) for tool-result messages. */
  toolMeta?: ToolMeta;
  /** De-duplicated sources for assistant messages (tool-covered sources removed). */
  displaySources?: SourceReference[];
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute right-2 top-2 rounded-md bg-zinc-300/80 dark:bg-zinc-700/80 p-1.5 text-zinc-500 dark:text-zinc-400 opacity-0 transition-opacity hover:text-zinc-800 dark:hover:text-zinc-200 group-hover:opacity-100"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

// ── Helpers for compact tool-result cards ─────────────────────────

/** Derive source_file paths from a tool call's metadata and result. */
function getToolSourceFiles(
  toolMeta: ToolMeta,
  content: string
): string[] {
  if (toolMeta.name === "document_read") {
    const filename = toolMeta.args.filename as string | undefined;
    return filename ? [`documents/${filename}`] : [];
  }
  if (toolMeta.name === "memory_read") {
    const d = toolMeta.args.date as string | undefined;
    if (d) return [`daily/${d}.md`];
    return [`daily/${new Date().toISOString().split("T")[0]}.md`];
  }
  if (toolMeta.name === "memory_search") {
    try {
      const data = JSON.parse(content);
      const files = new Set<string>();
      for (const r of data.results ?? []) {
        if (r.source_file) files.add(r.source_file);
      }
      return Array.from(files);
    } catch {
      return [];
    }
  }
  return [];
}

/** A human-friendly action label for the tool. */
function toolActionLabel(toolName: string): string {
  switch (toolName) {
    case "document_read":
      return "Read document";
    case "document_list":
      return "Listed documents";
    case "memory_read":
      return "Read memory";
    case "memory_search":
      return "Searched memories";
    default:
      return "Tool result";
  }
}

// ── Component ────────────────────────────────────────────────────

export default function MessageBubble({
  message,
  toolMeta,
  displaySources,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const isStreaming = "isStreaming" in message && message.isStreaming;
  const thinking =
    "thinking" in message ? (message.thinking ?? "") : "";
  const content = message.content || "";
  const sources = "sources" in message ? message.sources : null;

  // ── Tool result: compact citation card for document/memory tools ──
  if (isTool) {
    const isDocumentTool = toolMeta && DOCUMENT_TOOLS.has(toolMeta.name);

    if (isDocumentTool) {
      const sourceFiles = getToolSourceFiles(toolMeta, content);

      return (
        <div className="flex gap-3 px-4 py-2">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-500">
            <Wrench size={14} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-amber-600 dark:text-amber-500 mb-1.5">
              {toolActionLabel(toolMeta.name)}
            </p>
            <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30 overflow-hidden">
              {sourceFiles.length > 0 ? (
                sourceFiles.map((sf) => {
                  const href = sourceHref(sf);
                  const label = sourceLabel(sf);

                  const inner = (
                    <div className="flex items-center gap-2.5 px-3 py-2.5 transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/30">
                      <SourceIcon sourceFile={sf} />
                      <span className="truncate text-xs font-medium text-zinc-700 dark:text-zinc-300 flex-1">
                        {label}
                      </span>
                      <span
                        className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${typeBadgeClasses(
                          sf
                        )}`}
                      >
                        {typeLabel(sf)}
                      </span>
                      {href && (
                        <ExternalLink
                          size={12}
                          className="shrink-0 text-zinc-400 dark:text-zinc-500"
                        />
                      )}
                    </div>
                  );

                  return href ? (
                    <Link key={sf} href={href} className="block">
                      {inner}
                    </Link>
                  ) : (
                    <div key={sf}>{inner}</div>
                  );
                })
              ) : (
                <div className="px-3 py-2.5 text-xs text-zinc-500">
                  No results found.
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    // Workflow tool results: render with status badges and approval cards
    if (toolMeta && WORKFLOW_TOOLS.has(toolMeta.name)) {
      let parsed: Record<string, unknown> = {};
      try { parsed = JSON.parse(content); } catch {}

      const runId = parsed.run_id as string | undefined;
      const status = parsed.status as string | undefined;
      const workflowName = parsed.workflow as string | undefined;

      if (toolMeta.name === "workflow_run" && runId) {
        return (
          <div className="flex gap-3 px-4 py-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
              <Wrench size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-xs font-medium text-blue-600 dark:text-blue-400">
                  Workflow Started
                </p>
                {status && <WorkflowStatusBadge status={status as "pending" | "running"} />}
              </div>
              <div className="rounded-lg bg-zinc-100 dark:bg-zinc-800/50 p-3 text-xs text-zinc-700 dark:text-zinc-300">
                <p>{parsed.message as string}</p>
              </div>
            </div>
          </div>
        );
      }

      if (toolMeta.name === "workflow_status" && runId) {
        return (
          <div className="flex gap-3 px-4 py-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
              <Wrench size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-xs font-medium text-blue-600 dark:text-blue-400">
                  Workflow Status: {workflowName}
                </p>
                {status && <WorkflowStatusBadge status={status as "running" | "completed" | "failed"} />}
              </div>
              {parsed.error && (
                <p className="text-xs text-red-500 mt-1">{parsed.error as string}</p>
              )}
            </div>
          </div>
        );
      }

      if (toolMeta.name === "workflow_approve" && runId) {
        return (
          <div className="flex gap-3 px-4 py-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400">
              <Wrench size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400 mb-1">
                {parsed.action as string}
              </p>
              <p className="text-xs text-zinc-600 dark:text-zinc-400">{parsed.message as string}</p>
            </div>
          </div>
        );
      }

      if (toolMeta.name === "workflow_list") {
        const workflows = (parsed.workflows || []) as Array<Record<string, unknown>>;
        return (
          <div className="flex gap-3 px-4 py-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
              <Wrench size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">
                Available Workflows ({workflows.length})
              </p>
              <div className="rounded-lg bg-zinc-100 dark:bg-zinc-800/50 p-2 text-xs space-y-1">
                {workflows.map((w) => (
                  <div key={w.name as string} className="flex items-center gap-2">
                    <span className="font-mono font-medium text-zinc-700 dark:text-zinc-300">{w.name as string}</span>
                    {w.schedule && <span className="text-zinc-400 text-[10px]">(scheduled)</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      }
    }

    // Fallback: non-document tool results render as raw text
    return (
      <div className="flex gap-3 px-4 py-2">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-500">
          <Wrench size={14} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-amber-600 dark:text-amber-500 mb-1">Tool Result</p>
          <pre className="rounded-lg bg-zinc-100 dark:bg-zinc-800/50 p-3 text-xs text-zinc-700 dark:text-zinc-300 overflow-x-auto whitespace-pre-wrap">
            {content}
          </pre>
        </div>
      </div>
    );
  }

  // ── Determine which sources to show on this message ──
  // displaySources (passed from MessageList, deduped) takes priority;
  // fall back to message.sources for streaming messages or when
  // displaySources isn't provided.
  const effectiveSources =
    displaySources !== undefined ? displaySources : sources;

  return (
    <div
      className={`flex gap-3 px-4 py-4 ${
        isUser ? "" : "bg-zinc-50 dark:bg-zinc-800/30"
      }`}
    >
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-500"
        }`}
      >
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>

      <div className="min-w-0 flex-1">
        {!isUser && (thinking || isStreaming) && (
          <ThinkingIndicator thinking={thinking} isStreaming={isStreaming && !content} />
        )}

        {content ? (
          <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:p-0 prose-pre:bg-transparent">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeString = String(children).replace(/\n$/, "");

                  if (match) {
                    return (
                      <div className="group relative my-2 rounded-lg overflow-hidden">
                        <div className="flex items-center justify-between bg-zinc-200 dark:bg-zinc-800 px-4 py-1.5 text-xs text-zinc-500 dark:text-zinc-400">
                          <span>{match[1]}</span>
                        </div>
                        <CopyButton text={codeString} />
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match[1]}
                          PreTag="div"
                          customStyle={{
                            margin: 0,
                            borderRadius: 0,
                            background: "#1e1e2e",
                          }}
                        >
                          {codeString}
                        </SyntaxHighlighter>
                      </div>
                    );
                  }

                  return (
                    <code
                      className="rounded bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 text-sm text-zinc-700 dark:text-zinc-300"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        ) : isStreaming ? (
          <div className="flex items-center gap-1.5 text-zinc-400 dark:text-zinc-500">
            <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 dark:bg-zinc-500 [animation-delay:0ms]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 dark:bg-zinc-500 [animation-delay:150ms]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 dark:bg-zinc-500 [animation-delay:300ms]" />
          </div>
        ) : null}

        {/* Document/memory source citations (de-duplicated) */}
        {!isUser && effectiveSources && effectiveSources.length > 0 && (
          <SourcesCitation sources={effectiveSources} />
        )}
      </div>
    </div>
  );
}
