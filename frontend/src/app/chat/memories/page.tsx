"use client";

import { useRouter } from "next/navigation";
import { Brain, Calendar, FileText, Loader2 } from "lucide-react";
import { useMemories } from "@/lib/hooks/useMemories";

export function groupMemoriesByDate(
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
      <div className="flex items-center gap-3 px-6 py-5">
        <Brain size={18} className="text-blue-400" strokeWidth={1.5} />
        <h1 className="text-lg font-semibold text-foreground/85 tracking-tight">Memories</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-2">
        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={20} className="animate-spin text-foreground/20" />
          </div>
        )}

        {!loading && memories && (
          <div className="mx-auto max-w-2xl space-y-8">
            {memories.long_term.exists && (
              <div>
                <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-foreground/25">
                  Long-term Memory
                </h2>
                <button
                  onClick={() => router.push("/chat/memories/long-term")}
                  className="flex w-full items-center gap-3 rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3.5 text-left transition-all hover:bg-foreground/[0.07] hover:ring-foreground/[0.1]"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-400/10">
                    <Brain size={16} className="text-blue-400" strokeWidth={1.5} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground/75">
                      MEMORY.md
                    </p>
                    <p className="text-xs text-foreground/30">
                      Curated long-term facts and preferences
                    </p>
                  </div>
                  {memories.long_term.access_count > 0 && (
                    <span className="shrink-0 rounded-full bg-foreground/[0.06] px-2.5 py-1 text-[11px] font-medium text-foreground/30">
                      {memories.long_term.access_count} access
                      {memories.long_term.access_count !== 1 ? "es" : ""}
                    </span>
                  )}
                </button>
              </div>
            )}

            {memoryGroups.map((group) => (
              <div key={group.label}>
                <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-foreground/25">
                  {group.label}
                </h2>
                <div className="space-y-1.5">
                  {group.items.map((mem) => (
                    <button
                      key={mem.date}
                      onClick={() =>
                        router.push(`/chat/memories/daily/${mem.date}`)
                      }
                      className="flex w-full items-center gap-3 rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3.5 text-left transition-all hover:bg-foreground/[0.07] hover:ring-foreground/[0.1]"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.06]">
                        <Calendar size={16} className="text-foreground/40" strokeWidth={1.5} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground/75">
                          {mem.date}
                        </p>
                        <p className="text-xs text-foreground/30">Daily log</p>
                      </div>
                      {mem.access_count > 0 && (
                        <span className="shrink-0 rounded-full bg-foreground/[0.06] px-2.5 py-1 text-[11px] font-medium text-foreground/30">
                          {mem.access_count} access
                          {mem.access_count !== 1 ? "es" : ""}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ))}

            {memoryGroups.length === 0 && !memories.long_term.exists && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-foreground/[0.04]">
                  <FileText size={24} className="text-foreground/15" strokeWidth={1.5} />
                </div>
                <p className="text-sm font-medium text-foreground/40">
                  No memories yet
                </p>
                <p className="mt-1.5 max-w-xs text-xs text-foreground/20">
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
