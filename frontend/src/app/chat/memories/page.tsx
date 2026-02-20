"use client";

import { useRouter } from "next/navigation";
import { Brain, Calendar, FileText, Loader2 } from "lucide-react";
import { useMemories } from "@/lib/hooks/useMemories";

function groupMemoriesByDate(
  daily: { date: string; source_file: string; access_count: number }[]
) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const lastWeek = new Date(today.getTime() - 7 * 86400000);
  const lastMonth = new Date(today.getTime() - 30 * 86400000);

  const groups: {
    label: string;
    items: { date: string; source_file: string; access_count: number }[];
  }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Last 7 Days", items: [] },
    { label: "Last 30 Days", items: [] },
    { label: "Older", items: [] },
  ];

  for (const mem of daily) {
    const d = new Date(mem.date + "T00:00:00");
    if (d >= today) groups[0].items.push(mem);
    else if (d >= yesterday) groups[1].items.push(mem);
    else if (d >= lastWeek) groups[2].items.push(mem);
    else if (d >= lastMonth) groups[3].items.push(mem);
    else groups[4].items.push(mem);
  }

  return groups.filter((g) => g.items.length > 0);
}

export default function MemoriesPage() {
  const router = useRouter();
  const { memories, loading } = useMemories();

  const memoryGroups = memories ? groupMemoriesByDate(memories.daily) : [];

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <Brain size={20} className="text-purple-400" />
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Memories</h1>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-2 text-zinc-500">
              <Loader2 size={20} className="animate-spin" />
              <span className="text-sm">Loading memories...</span>
            </div>
          </div>
        )}

        {!loading && memories && (
          <div className="mx-auto max-w-2xl space-y-6">
            {/* Long-term memory (MEMORY.md) */}
            {memories.long_term.exists && (
              <div>
                <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Long-term Memory
                </h2>
                <button
                  onClick={() => router.push("/chat/memories/long-term")}
                  className="flex w-full items-center gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 px-4 py-3 text-left transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-purple-500/10">
                    <Brain size={18} className="text-purple-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                      MEMORY.md
                    </p>
                    <p className="text-xs text-zinc-500">
                      Curated long-term facts and preferences
                    </p>
                  </div>
                  {memories.long_term.access_count > 0 && (
                    <span className="shrink-0 rounded-full bg-zinc-200 dark:bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                      {memories.long_term.access_count} access
                      {memories.long_term.access_count !== 1 ? "es" : ""}
                    </span>
                  )}
                </button>
              </div>
            )}

            {/* Daily logs grouped by date */}
            {memoryGroups.map((group) => (
              <div key={group.label}>
                <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {group.label}
                </h2>
                <div className="space-y-1.5">
                  {group.items.map((mem) => (
                    <button
                      key={mem.date}
                      onClick={() =>
                        router.push(`/chat/memories/daily/${mem.date}`)
                      }
                      className="flex w-full items-center gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 px-4 py-3 text-left transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-500/10">
                        <Calendar size={18} className="text-blue-400" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                          {mem.date}
                        </p>
                        <p className="text-xs text-zinc-500">Daily log</p>
                      </div>
                      {mem.access_count > 0 && (
                        <span className="shrink-0 rounded-full bg-zinc-200 dark:bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                          {mem.access_count} access
                          {mem.access_count !== 1 ? "es" : ""}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ))}

            {/* Empty state */}
            {memoryGroups.length === 0 && !memories.long_term.exists && (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-zinc-200/50 dark:bg-zinc-800/50">
                  <FileText size={28} className="text-zinc-400 dark:text-zinc-600" />
                </div>
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  No memories yet
                </p>
                <p className="mt-1 max-w-xs text-xs text-zinc-500">
                  Start chatting and the AI will create memories automatically.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
