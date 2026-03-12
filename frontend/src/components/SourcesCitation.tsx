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

export function sourceLabel(sourceFile: string): string {
  if (sourceFile === "MEMORY.md") return "Long-term Memory";
  if (sourceFile.startsWith("daily/")) {
    const datePart = sourceFile.replace("daily/", "").replace(".md", "");
    try {
      const d = new Date(datePart + "T00:00:00");
      return `Daily Log -- ${d.toLocaleDateString("en-US", {
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

export function SourceIcon({ sourceFile }: { sourceFile: string }) {
  if (sourceFile === "MEMORY.md") {
    return <BookOpen size={13} className="text-blue-400/70" strokeWidth={1.5} />;
  }
  if (sourceFile.startsWith("daily/")) {
    return <Calendar size={13} className="text-blue-400/70" strokeWidth={1.5} />;
  }
  if (sourceFile.startsWith("documents/")) {
    const ext = sourceFile.split(".").pop()?.toLowerCase();
    if (ext === "pdf") return <File size={13} className="text-red-400/70" strokeWidth={1.5} />;
    if (ext === "xlsx" || ext === "xls")
      return <FileSpreadsheet size={13} className="text-emerald-400/70" strokeWidth={1.5} />;
    if (ext === "docx" || ext === "doc")
      return <FileText size={13} className="text-blue-400/70" strokeWidth={1.5} />;
  }
  return <FileText size={13} className="text-foreground/30" strokeWidth={1.5} />;
}

export function sourceHref(sourceFile: string): string | null {
  if (sourceFile === "MEMORY.md") {
    return "/chat/context";
  }
  if (sourceFile.startsWith("daily/")) {
    return "/chat/context";
  }
  if (sourceFile.startsWith("documents/")) {
    return "/chat/context";
  }
  return null;
}

export function typeBadgeClasses(sourceFile: string): string {
  if (sourceFile === "MEMORY.md") {
    return "bg-blue-400/10 text-blue-400/70";
  }
  if (sourceFile.startsWith("daily/")) {
    return "bg-blue-400/10 text-blue-400/70";
  }
  if (sourceFile.startsWith("documents/")) {
    return "bg-emerald-400/10 text-emerald-400/70";
  }
  return "bg-foreground/[0.06] text-foreground/30";
}

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

  const previewCount = 2;
  const visibleSources = expanded ? sources : sources.slice(0, previewCount);
  const hasMore = sources.length > previewCount;

  return (
    <div className="mt-3 rounded-xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3.5 py-2 text-left transition-colors hover:bg-foreground/[0.04]"
      >
        <FileText size={13} className="shrink-0 text-blue-400/60" strokeWidth={1.5} />
        <span className="text-[11px] font-medium text-foreground/40">
          {sources.length} {sources.length === 1 ? "source" : "sources"} referenced
        </span>
        <span className="ml-auto shrink-0 text-foreground/20">
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </span>
      </button>

      <div className="border-t border-foreground/[0.05]">
        {visibleSources.map((source) => {
          const href = sourceHref(source.source_file);
          const label = sourceLabel(source.source_file);

          const inner = (
            <div className="flex items-center gap-2.5 px-3.5 py-2.5 transition-colors hover:bg-foreground/[0.04]">
              <SourceIcon sourceFile={source.source_file} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-foreground/55">
                  {label}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${typeBadgeClasses(
                  source.source_file
                )}`}
              >
                {typeLabel(source.source_file)}
              </span>
              {href && (
                <ExternalLink
                  size={11}
                  className="shrink-0 text-foreground/15"
                  strokeWidth={1.5}
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

        {hasMore && !expanded && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(true);
            }}
            className="flex w-full items-center justify-center gap-1 px-3 py-1.5 text-[11px] text-foreground/25 hover:text-foreground/40 hover:bg-foreground/[0.04]"
          >
            +{sources.length - previewCount} more
          </button>
        )}
      </div>
    </div>
  );
}
