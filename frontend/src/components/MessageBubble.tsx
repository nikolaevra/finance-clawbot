"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, Wrench, ExternalLink, ChevronRight, ChevronDown } from "lucide-react";
import { useState, type ReactNode, type HTMLAttributes } from "react";
import Link from "next/link";
import type { Message, StreamingMessage, ToolMeta, SourceReference } from "@/types";
import ThinkingIndicator from "./ThinkingIndicator";
import SourcesCitation, {
  sourceLabel,
  sourceHref,
  SourceIcon,
  typeLabel,
  typeBadgeClasses,
} from "./SourcesCitation";

const DOCUMENT_TOOLS = new Set([
  "document_read",
  "document_list",
  "memory_read",
  "memory_search",
]);

interface MessageBubbleProps {
  message: Message | StreamingMessage;
  toolMeta?: ToolMeta;
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
      className="absolute right-2.5 top-2.5 rounded-lg bg-foreground/[0.08] p-1.5 text-foreground/30 opacity-0 transition-all hover:text-foreground/70 hover:bg-foreground/[0.12] group-hover:opacity-100"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
}

export function getToolSourceFiles(
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

export function toolActionLabel(toolName: string): string {
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

export function humanizeToolName(toolName: string): string {
  return toolName.replaceAll("_", " ");
}

export function oneLine(text: string, maxLen = 90): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  return cleaned.length > maxLen ? `${cleaned.slice(0, maxLen - 1)}…` : cleaned;
}

const MARKDOWN_PLUGINS = [remarkGfm, remarkBreaks];

export function toolResultPreview(toolMeta: ToolMeta | undefined, content: string): string {
  const toolName = toolMeta?.name ?? "tool";
  const prettyTool = humanizeToolName(toolName);

  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    const used = typeof parsed.tool_used === "string" ? parsed.tool_used : toolName;
    const prettyUsed = humanizeToolName(used);

    if (typeof parsed.error === "string" && parsed.error) {
      return `${prettyUsed}: error - ${oneLine(parsed.error, 72)}`;
    }
    if (typeof parsed.message === "string" && parsed.message) {
      return `${prettyUsed}: ${oneLine(parsed.message, 72)}`;
    }
    if (typeof parsed.total === "number") {
      return `${prettyUsed}: ${parsed.total} total`;
    }

    for (const [key, value] of Object.entries(parsed)) {
      if (Array.isArray(value)) {
        return `${prettyUsed}: ${value.length} ${key}`;
      }
    }

    const keys = Object.keys(parsed);
    if (keys.length > 0) {
      return `${prettyUsed}: ${keys.slice(0, 3).join(", ")}`;
    }
  } catch {
    // non-JSON payloads are fine; use text fallback below.
  }

  return `${prettyTool}: ${oneLine(content, 72) || "completed"}`;
}

export default function MessageBubble({
  message,
  toolMeta,
  displaySources,
}: MessageBubbleProps) {
  const [toolExpanded, setToolExpanded] = useState(false);
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const isStreaming = "isStreaming" in message && message.isStreaming;
  const thinking =
    "thinking" in message ? (message.thinking ?? "") : "";
  const content = message.content || "";
  const sources = "sources" in message ? message.sources : null;

  const renderCollapsibleToolResult = (
    title: string,
    body: React.ReactNode,
    headerRight?: React.ReactNode,
    titleClassName = "text-foreground/30",
    preview?: string
  ) => (
    <div className="flex justify-start px-4 py-1.5">
      <div className="max-w-[85%] w-full">
        <button
          type="button"
          onClick={() => setToolExpanded((prev) => !prev)}
          className="mb-1.5 ml-1 inline-flex items-center gap-1.5 text-[11px] font-medium hover:text-foreground/60 transition-colors"
          aria-expanded={toolExpanded}
        >
          {toolExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <Wrench size={11} />
          <span className={titleClassName}>{title}</span>
          {!toolExpanded && preview ? (
            <span className="max-w-[28rem] truncate text-foreground/35">
              {preview}
            </span>
          ) : null}
          {headerRight}
          <span className="text-foreground/20">
            {toolExpanded ? "Collapse" : "Expand"}
          </span>
        </button>
        {toolExpanded ? body : null}
      </div>
    </div>
  );

  if (isTool) {
    const isDocumentTool = toolMeta && DOCUMENT_TOOLS.has(toolMeta.name);
    if (isDocumentTool) {
      const sourceFiles = getToolSourceFiles(toolMeta, content);

      const preview =
        sourceFiles.length > 0
          ? `${humanizeToolName(toolMeta.name)}: ${sourceFiles.length} source file${sourceFiles.length === 1 ? "" : "s"}`
          : `${humanizeToolName(toolMeta.name)}: no results`;

      return renderCollapsibleToolResult(
        toolActionLabel(toolMeta.name),
        <div className="rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] overflow-hidden">
          {sourceFiles.length > 0 ? (
            sourceFiles.map((sf) => {
              const href = sourceHref(sf);
              const label = sourceLabel(sf);

              const inner = (
                <div className="flex items-center gap-2.5 px-3.5 py-2.5 transition-colors hover:bg-foreground/[0.04]">
                  <SourceIcon sourceFile={sf} />
                  <span className="truncate text-xs font-medium text-foreground/60 flex-1">
                    {label}
                  </span>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${typeBadgeClasses(sf)}`}
                  >
                    {typeLabel(sf)}
                  </span>
                  {href && (
                    <ExternalLink
                      size={11}
                      className="shrink-0 text-foreground/20"
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
            <div className="px-3.5 py-2.5 text-xs text-foreground/30">
              No results found.
            </div>
          )}
        </div>,
        undefined,
        "text-foreground/30",
        preview
      );
    }

    return renderCollapsibleToolResult(
      "Tool Result",
      <pre className="rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3 text-xs text-foreground/50 overflow-x-auto whitespace-pre-wrap">
        {content}
      </pre>,
      undefined,
      "text-foreground/30",
      toolResultPreview(toolMeta, content)
    );
  }

  const effectiveSources =
    displaySources !== undefined ? displaySources : sources;
  const markdownHrClassName = isUser
    ? "my-7 border-0 border-t border-white/30"
    : "my-8 border-0 border-t border-foreground/[0.22]";
  const markdownTableClassName = isUser
    ? "w-full min-w-[30rem] border-collapse border border-white/30"
    : "w-full min-w-[30rem] border-collapse border border-foreground/[0.18]";

  const markdownComponents = {
    hr(props: HTMLAttributes<HTMLHRElement>) {
      return <hr className={markdownHrClassName} {...props} />;
    },
    table({ children }: { children?: ReactNode }) {
      return (
        <div className="my-5 w-full overflow-x-auto">
          <table className={markdownTableClassName}>
            {children}
          </table>
        </div>
      );
    },
    code({
      className,
      children,
      ...props
    }: HTMLAttributes<HTMLElement> & { children?: ReactNode }) {
      const match = /language-(\w+)/.exec(className || "");
      const codeString = String(children).replace(/\n$/, "");

      if (match) {
        return (
          <div className="group relative my-3 rounded-xl overflow-hidden ring-1 ring-foreground/[0.08] shadow-lg shadow-black/20">
            <div className="flex items-center justify-between bg-foreground/[0.06] px-4 py-2 text-[11px] text-foreground/30 font-medium">
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
                background: "var(--card)",
                fontSize: "12.5px",
              }}
            >
              {codeString}
            </SyntaxHighlighter>
          </div>
        );
      }

      return (
        <code
          className="rounded-md bg-foreground/[0.08] px-1.5 py-0.5 text-[13px] text-foreground/70 font-mono"
          {...props}
        >
          {children}
        </code>
      );
    },
  };

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1.5">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-blue-500 px-4 py-2.5 text-white shadow-md shadow-blue-500/10">
          <div className="prose prose-sm max-w-none leading-relaxed prose-p:my-[1.25rem] prose-p:leading-7 prose-p:text-white prose-strong:text-white prose-headings:my-3 prose-headings:text-white prose-ul:my-2 prose-ul:list-disc prose-ul:pl-5 prose-ol:my-2 prose-ol:list-decimal prose-ol:pl-5 prose-li:my-0.5 prose-li:text-blue-50 prose-code:rounded prose-code:bg-white/10 prose-code:px-1 prose-code:py-0.5 prose-code:text-blue-50 prose-a:text-blue-100 prose-a:no-underline hover:prose-a:underline prose-hr:my-7 prose-hr:border-white/30 prose-table:my-5 prose-table:w-full prose-table:border-collapse prose-table:border prose-table:border-white/30 prose-th:border prose-th:border-white/35 prose-th:px-2 prose-th:py-1 prose-th:text-left prose-th:text-white prose-td:border prose-td:border-white/25 prose-td:px-2 prose-td:py-1 prose-td:text-blue-50">
            <ReactMarkdown remarkPlugins={MARKDOWN_PLUGINS} components={markdownComponents}>
              {content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start px-4 py-2.5">
      <div className="w-full">
        {(thinking || isStreaming) && (
          <ThinkingIndicator thinking={thinking} isStreaming={isStreaming && !content} />
        )}

        {content ? (
          <div className="rounded-2xl bg-foreground/[0.03] px-5 py-4 ring-1 ring-foreground/[0.08] shadow-sm shadow-black/5">
            <div className="prose prose-sm dark:prose-invert max-w-none leading-relaxed prose-p:my-[1.25rem] prose-p:leading-7 prose-ul:my-3 prose-ul:list-disc prose-ul:pl-6 prose-ol:my-3 prose-ol:list-decimal prose-ol:pl-6 prose-li:my-1 prose-li:marker:text-foreground/45 prose-blockquote:my-4 prose-blockquote:border-l-2 prose-blockquote:border-foreground/20 prose-blockquote:pl-4 prose-blockquote:text-foreground/75 prose-pre:my-4 prose-pre:p-0 prose-pre:bg-transparent prose-headings:mt-6 prose-headings:mb-3 prose-headings:text-foreground/90 prose-hr:my-8 prose-hr:border-foreground/[0.22] prose-table:my-5 prose-table:w-full prose-table:border-collapse prose-table:border prose-table:border-foreground/[0.18] prose-th:border prose-th:border-foreground/[0.18] prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-semibold prose-th:text-foreground/80 prose-td:px-3 prose-td:py-2 prose-td:align-top prose-td:border prose-td:border-foreground/[0.14] prose-strong:text-foreground/95 prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline">
              <ReactMarkdown
                remarkPlugins={MARKDOWN_PLUGINS}
                components={markdownComponents}
              >
                {content}
              </ReactMarkdown>
            </div>

            {effectiveSources && effectiveSources.length > 0 && (
              <div className="mt-3">
                <SourcesCitation sources={effectiveSources} />
              </div>
            )}
          </div>
        ) : isStreaming ? (
          <div className="flex items-center gap-1 py-2">
            <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/20 [animation-delay:0ms]" />
            <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/20 [animation-delay:150ms]" />
            <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/20 [animation-delay:300ms]" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
