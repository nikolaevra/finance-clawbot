"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Save, Check, Loader2, ArrowLeft, MessageSquare } from "lucide-react";
import type { MemoryAccessLogEntry } from "@/types";
import { fetchMemoryAccessLog } from "@/lib/api";

interface MemoryEditorProps {
  sourceFile: string;
  title: string;
  initialContent: string;
  onSave: (content: string) => Promise<void>;
}

export default function MemoryEditor({
  sourceFile,
  title,
  initialContent,
  onSave,
}: MemoryEditorProps) {
  const router = useRouter();
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [accessLog, setAccessLog] = useState<MemoryAccessLogEntry[]>([]);
  const [logLoading, setLogLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const log = await fetchMemoryAccessLog(sourceFile);
        if (!cancelled) setAccessLog(log);
      } catch {
        // best-effort
      } finally {
        if (!cancelled) setLogLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [sourceFile]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await onSave(content);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }, [content, onSave]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSave]);

  const conversationSummary = accessLog.reduce(
    (acc, entry) => {
      const existing = acc.find(
        (e) => e.conversation_id === entry.conversation_id
      );
      if (existing) {
        existing.count += 1;
      } else {
        acc.push({
          conversation_id: entry.conversation_id,
          conversation_title: entry.conversation_title,
          count: 1,
          last_accessed: entry.created_at,
        });
      }
      return acc;
    },
    [] as {
      conversation_id: string;
      conversation_title: string;
      count: number;
      last_accessed: string;
    }[]
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-foreground/[0.06]">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/chat/memories")}
            className="rounded-lg p-1.5 text-foreground/30 hover:text-foreground/60 hover:bg-foreground/[0.06]"
          >
            <ArrowLeft size={16} strokeWidth={1.5} />
          </button>
          <div>
            <h1 className="text-sm font-medium text-foreground/80">{title}</h1>
            <p className="text-[11px] text-foreground/25">{sourceFile}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <span className="text-xs text-red-400/80">{error}</span>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-sm font-medium transition-all ${
              saved
                ? "bg-emerald-400/10 text-emerald-400/80"
                : "bg-foreground/[0.06] text-foreground/60 hover:text-foreground/80 hover:bg-foreground/[0.1]"
            }`}
          >
            {saving ? (
              <Loader2 size={13} className="animate-spin" />
            ) : saved ? (
              <Check size={13} />
            ) : (
              <Save size={13} strokeWidth={1.5} />
            )}
            {saving ? "Saving..." : saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 resize-none bg-transparent p-5 font-mono text-sm text-foreground/70 outline-none placeholder:text-foreground/15 leading-relaxed"
            placeholder="Memory content..."
            spellCheck={false}
          />
        </div>

        <div className="hidden md:block w-72 shrink-0 border-l border-foreground/[0.06] overflow-y-auto">
          <div className="p-4">
            <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-foreground/25">
              Access Log
            </h2>

            {logLoading ? (
              <div className="flex items-center gap-2 text-xs text-foreground/25">
                <Loader2 size={12} className="animate-spin" />
                Loading...
              </div>
            ) : conversationSummary.length === 0 ? (
              <p className="text-[11px] text-foreground/20">
                No conversations have referenced this memory yet.
              </p>
            ) : (
              <>
                <p className="mb-3 text-[11px] text-foreground/30">
                  Referenced {accessLog.length} time
                  {accessLog.length !== 1 ? "s" : ""} across{" "}
                  {conversationSummary.length} conversation
                  {conversationSummary.length !== 1 ? "s" : ""}
                </p>
                <div className="space-y-1">
                  {conversationSummary.map((entry) => (
                    <button
                      key={entry.conversation_id}
                      onClick={() =>
                        router.push(`/chat/${entry.conversation_id}`)
                      }
                      className="flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-foreground/[0.04]"
                    >
                      <MessageSquare
                        size={12}
                        className="mt-0.5 shrink-0 text-foreground/25"
                        strokeWidth={1.5}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-foreground/50">
                          {entry.conversation_title}
                        </p>
                        <p className="text-[10px] text-foreground/20">
                          {entry.count} reference
                          {entry.count !== 1 ? "s" : ""}{" "}
                          /{" "}
                          {new Date(entry.last_accessed).toLocaleDateString()}
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
