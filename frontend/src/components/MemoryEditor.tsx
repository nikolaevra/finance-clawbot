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

  // Load access log
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const log = await fetchMemoryAccessLog(sourceFile);
        if (!cancelled) setAccessLog(log);
      } catch {
        // Access log is best-effort
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

  // Keyboard shortcut: Cmd/Ctrl + S to save
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

  // Deduplicate access log by conversation for the summary
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
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/chat/memories")}
            className="rounded-lg p-1.5 text-zinc-500 dark:text-zinc-400 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-zinc-700 dark:hover:text-zinc-200"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{title}</h1>
            <p className="text-xs text-zinc-500">{sourceFile}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <span className="text-xs text-red-500 dark:text-red-400">{error}</span>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              saved
                ? "bg-green-600/20 text-green-600 dark:text-green-400"
                : "bg-zinc-200 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 hover:bg-zinc-300 dark:hover:bg-zinc-700"
            }`}
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : saved ? (
              <Check size={14} />
            ) : (
              <Save size={14} />
            )}
            {saving ? "Saving..." : saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Editor */}
        <div className="flex flex-1 flex-col">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 resize-none bg-white dark:bg-zinc-950 p-4 font-mono text-sm text-zinc-800 dark:text-zinc-200 outline-none placeholder:text-zinc-400 dark:placeholder:text-zinc-600"
            placeholder="Memory content..."
            spellCheck={false}
          />
        </div>

        {/* Access log panel */}
        <div className="w-72 shrink-0 border-l border-zinc-200 dark:border-zinc-800 overflow-y-auto">
          <div className="p-3">
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Access Log
            </h2>

            {logLoading ? (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <Loader2 size={12} className="animate-spin" />
                Loading...
              </div>
            ) : conversationSummary.length === 0 ? (
              <p className="text-xs text-zinc-400 dark:text-zinc-600">
                No conversations have referenced this memory yet.
              </p>
            ) : (
              <>
                <p className="mb-3 text-xs text-zinc-500">
                  Referenced {accessLog.length} time
                  {accessLog.length !== 1 ? "s" : ""} across{" "}
                  {conversationSummary.length} conversation
                  {conversationSummary.length !== 1 ? "s" : ""}
                </p>
                <div className="space-y-1.5">
                  {conversationSummary.map((entry) => (
                    <button
                      key={entry.conversation_id}
                      onClick={() =>
                        router.push(`/chat/${entry.conversation_id}`)
                      }
                      className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800/50"
                    >
                      <MessageSquare
                        size={13}
                        className="mt-0.5 shrink-0 text-zinc-500"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-zinc-700 dark:text-zinc-300">
                          {entry.conversation_title}
                        </p>
                        <p className="text-[10px] text-zinc-500">
                          {entry.count} reference
                          {entry.count !== 1 ? "s" : ""}{" "}
                          &middot;{" "}
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
