"use client";

import { useState, useEffect, useCallback, use } from "react";
import { Loader2 } from "lucide-react";
import MemoryEditor from "@/components/MemoryEditor";
import {
  fetchDailyLog,
  updateDailyLog,
  fetchLongTermMemory,
  updateLongTermMemory,
} from "@/lib/api";

export default function MemoryPage({
  params,
}: {
  params: Promise<{ file: string[] }>;
}) {
  const { file } = use(params);

  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Determine which memory file to load
  const isLongTerm = file[0] === "long-term";
  const isDaily = file[0] === "daily" && file.length >= 2;
  const date = isDaily ? file[1] : null;

  const sourceFile = isLongTerm
    ? "MEMORY.md"
    : isDaily
      ? `daily/${date}.md`
      : "";

  const title = isLongTerm
    ? "Long-term Memory"
    : isDaily
      ? `Daily Log — ${date}`
      : "Memory";

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (isLongTerm) {
          const data = await fetchLongTermMemory();
          if (!cancelled) setContent(data.content);
        } else if (isDaily && date) {
          const data = await fetchDailyLog(date);
          if (!cancelled) setContent(data.content);
        } else {
          setError("Invalid memory path.");
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load memory"
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [isLongTerm, isDaily, date]);

  const handleSave = useCallback(
    async (newContent: string) => {
      if (isLongTerm) {
        await updateLongTermMemory(newContent);
      } else if (isDaily && date) {
        await updateDailyLog(date, newContent);
      }
    },
    [isLongTerm, isDaily, date]
  );

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex items-center gap-2 text-zinc-500">
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm">Loading memory...</span>
        </div>
      </div>
    );
  }

  if (error || content === null) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-red-400">{error || "Memory not found."}</p>
      </div>
    );
  }

  return (
    <MemoryEditor
      sourceFile={sourceFile}
      title={title}
      initialContent={content}
      onSave={handleSave}
    />
  );
}
