"use client";

import { useRouter } from "next/navigation";
import {
  LogOut,
  X,
  Menu,
  Brain,
  FileText,
  Calendar,
  MessageSquare,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { createClient } from "@/lib/supabase";
import type { MemoryListResponse } from "@/types";
import ThemeToggle from "./ThemeToggle";

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  memories: MemoryListResponse | null;
  memoriesLoading: boolean;
}

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

export default function Sidebar({
  isOpen,
  onToggle,
  memories,
  memoriesLoading,
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const isChatActive = pathname === "/chat" || pathname.match(/^\/chat\/[0-9a-f-]+/);

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  };

  const memoryGroups = memories ? groupMemoriesByDate(memories.daily) : [];

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onToggle}
        />
      )}

      {/* Mobile toggle button */}
      <button
        onClick={onToggle}
        className="fixed left-4 top-4 z-50 rounded-lg bg-zinc-200 dark:bg-zinc-800 p-2 text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 md:hidden"
      >
        {isOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-zinc-50 dark:bg-zinc-900 transition-transform duration-200 md:relative md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Navigation */}
        <div className="px-2 pt-3 pb-1 space-y-0.5">
          <button
            onClick={() => {
              router.push("/chat");
              if (isOpen) onToggle();
            }}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors ${
              isChatActive
                ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100"
                : "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 hover:text-zinc-700 dark:hover:text-zinc-200"
            }`}
          >
            <MessageSquare size={16} />
            Chat
          </button>
        </div>

        {/* Memories header */}
        <div className="flex items-center gap-2 px-4 pt-3 pb-1">
          <Brain size={14} className="text-purple-400" />
          <span className="text-xs font-medium text-zinc-500">Memories</span>
        </div>

        {/* Memories list */}
        <nav className="flex-1 overflow-y-auto px-2 pb-2">
          {memoriesLoading && (
            <div className="px-2 py-4 text-center text-xs text-zinc-500">
              Loading memories...
            </div>
          )}

          {!memoriesLoading && memories && (
            <>
              {/* Long-term memory (MEMORY.md) */}
              {memories.long_term.exists && (
                <div className="mb-2">
                  <h3 className="px-2 py-1.5 text-xs font-medium text-zinc-500">
                    Long-term Memory
                  </h3>
                  <button
                    onClick={() => {
                      router.push("/chat/memory/long-term");
                      if (isOpen) onToggle();
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-zinc-500 dark:text-zinc-400 transition-colors hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 hover:text-zinc-700 dark:hover:text-zinc-200"
                  >
                    <Brain size={14} className="shrink-0 text-purple-400" />
                    <span className="truncate">MEMORY.md</span>
                    {memories.long_term.access_count > 0 && (
                      <span className="ml-auto shrink-0 rounded-full bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
                        {memories.long_term.access_count}
                      </span>
                    )}
                  </button>
                </div>
              )}

              {/* Daily logs grouped by date */}
              {memoryGroups.map((group) => (
                <div key={group.label} className="mb-2">
                  <h3 className="px-2 py-1.5 text-xs font-medium text-zinc-500">
                    {group.label}
                  </h3>
                  {group.items.map((mem) => (
                    <button
                      key={mem.date}
                      onClick={() => {
                        router.push(`/chat/memory/daily/${mem.date}`);
                        if (isOpen) onToggle();
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-zinc-500 dark:text-zinc-400 transition-colors hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 hover:text-zinc-700 dark:hover:text-zinc-200"
                    >
                      <Calendar
                        size={14}
                        className="shrink-0 text-blue-400"
                      />
                      <span className="truncate">{mem.date}</span>
                      {mem.access_count > 0 && (
                        <span className="ml-auto shrink-0 rounded-full bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
                          {mem.access_count}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              ))}

              {/* Empty state */}
              {memoryGroups.length === 0 &&
                !memories.long_term.exists && (
                  <div className="px-2 py-8 text-center text-xs text-zinc-500">
                    <FileText
                      size={24}
                      className="mx-auto mb-2 text-zinc-400 dark:text-zinc-600"
                    />
                    No memories yet. Start chatting and the AI will create
                    memories automatically.
                  </div>
                )}
            </>
          )}
        </nav>

        {/* Bottom actions */}
        <div className="border-t border-zinc-200 dark:border-zinc-800 p-3 space-y-1">
          <div className="flex items-center justify-between px-2">
            <span className="text-xs text-zinc-500">Theme</span>
            <ThemeToggle />
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-zinc-500 dark:text-zinc-400 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-zinc-700 dark:hover:text-zinc-200"
          >
            <LogOut size={16} />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
