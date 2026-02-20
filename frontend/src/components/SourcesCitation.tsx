"use client";

import { useState } from "react";
import Link from "next/link";
import {
  FileText,
  File,
  FileSpreadsheet,
  BookOpen,
  Calendar,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
import type { SourceReference } from "@/types";

interface SourcesCitationProps {
  sources: SourceReference[];
}

/** Derive a human-readable label from a source_file path. */
export function sourceLabel(sourceFile: string): string {
  if (sourceFile === "MEMORY.md") return "Long-term Memory";
  if (sourceFile.startsWith("daily/")) {
    // "daily/2025-01-15.md" → "Daily Log — Jan 15, 2025"
    const datePart = sourceFile.replace("daily/", "").replace(".md", "");
    try {
      const d = new Date(datePart + "T00:00:00");
      return `Daily Log — ${d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })}`;
    } catch {
      return sourceFile;
    }
  }
  if (sourceFile.startsWith("documents/")) {
    return sourceFile.replace("documents/", "");
  }
  return sourceFile;
}

/** Get the appropriate icon for a source type. */
export function SourceIcon({ sourceFile }: { sourceFile: string }) {
  if (sourceFile === "MEMORY.md") {
    return <BookOpen size={14} className="text-purple-500 dark:text-purple-400" />;
  }
  if (sourceFile.startsWith("daily/")) {
    return <Calendar size={14} className="text-blue-500 dark:text-blue-400" />;
  }
  if (sourceFile.startsWith("documents/")) {
    const ext = sourceFile.split(".").pop()?.toLowerCase();
    if (ext === "pdf") return <File size={14} className="text-red-400" />;
    if (ext === "xlsx" || ext === "xls")
      return <FileSpreadsheet size={14} className="text-green-400" />;
    if (ext === "docx" || ext === "doc")
      return <FileText size={14} className="text-blue-400" />;
  }
  return <FileText size={14} className="text-zinc-400" />;
}

/** Build a link path for a source file. */
export function sourceHref(sourceFile: string): string | null {
  if (sourceFile === "MEMORY.md") {
    return "/chat/memories/MEMORY.md";
  }
  if (sourceFile.startsWith("daily/")) {
    return `/chat/memories/${sourceFile}`;
  }
  if (sourceFile.startsWith("documents/")) {
    return "/chat/documents";
  }
  return null;
}

/** Get a color class for the source type badge. */
export function typeBadgeClasses(sourceFile: string): string {
  if (sourceFile === "MEMORY.md") {
    return "bg-purple-500/10 text-purple-600 dark:text-purple-400";
  }
  if (sourceFile.startsWith("daily/")) {
    return "bg-blue-500/10 text-blue-600 dark:text-blue-400";
  }
  if (sourceFile.startsWith("documents/")) {
    return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  }
  return "bg-zinc-500/10 text-zinc-600 dark:text-zinc-400";
}

/** Get a short type label. */
export function typeLabel(sourceFile: string): string {
  if (sourceFile === "MEMORY.md") return "Memory";
  if (sourceFile.startsWith("daily/")) return "Daily Log";
  if (sourceFile.startsWith("documents/")) {
    const ext = sourceFile.split(".").pop()?.toUpperCase();
    return ext || "Document";
  }
  return "Source";
}

export default function SourcesCitation({ sources }: SourcesCitationProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  // Show first 2 sources inline, rest in expanded view
  const previewCount = 2;
  const visibleSources = expanded ? sources : sources.slice(0, previewCount);
  const hasMore = sources.length > previewCount;

  return (
    <div className="mt-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/30"
      >
        <FileText size={14} className="shrink-0 text-emerald-500 dark:text-emerald-400" />
        <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
          {sources.length} {sources.length === 1 ? "source" : "sources"} referenced
        </span>
        <span className="ml-auto shrink-0 text-zinc-400 dark:text-zinc-500">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {/* Source list */}
      <div className="border-t border-zinc-200/50 dark:border-zinc-800/50">
        {visibleSources.map((source, idx) => {
          const href = sourceHref(source.source_file);
          const label = sourceLabel(source.source_file);

          const inner = (
            <div className="flex items-center gap-2.5 px-3 py-2 transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/30">
              <SourceIcon sourceFile={source.source_file} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-zinc-700 dark:text-zinc-300">
                  {label}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${typeBadgeClasses(
                  source.source_file
                )}`}
              >
                {typeLabel(source.source_file)}
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
            <Link
              key={source.source_file}
              href={href}
              className="block"
            >
              {inner}
            </Link>
          ) : (
            <div key={source.source_file}>{inner}</div>
          );
        })}

        {/* "Show more" / "Show less" */}
        {hasMore && !expanded && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(true);
            }}
            className="flex w-full items-center justify-center gap-1 px-3 py-1.5 text-xs text-zinc-500 transition-colors hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100/50 dark:hover:bg-zinc-800/30"
          >
            +{sources.length - previewCount} more
          </button>
        )}
      </div>
    </div>
  );
}
