"use client";

import { usePathname, useRouter } from "next/navigation";
import { Brain, MessageSquare, FileText, Link2, LogOut, Receipt, Workflow, Sparkles } from "lucide-react";
import { createClient } from "@/lib/supabase";
import ThemeToggle from "./ThemeToggle";

const NAV_ITEMS = [
  {
    label: "Chat",
    href: "/chat",
    icon: MessageSquare,
    activeColor: "text-blue-400",
  },
  {
    label: "Memories",
    href: "/chat/memories",
    icon: Brain,
    activeColor: "text-purple-400",
  },
  {
    label: "Documents",
    href: "/chat/documents",
    icon: FileText,
    activeColor: "text-emerald-400",
  },
  {
    label: "Transactions",
    href: "/chat/transactions",
    icon: Receipt,
    activeColor: "text-cyan-400",
  },
  {
    label: "Workflows",
    href: "/chat/workflows",
    icon: Workflow,
    activeColor: "text-amber-400",
  },
  {
    label: "Skills",
    href: "/chat/skills",
    icon: Sparkles,
    activeColor: "text-violet-400",
  },
  {
    label: "Integrations",
    href: "/chat/integrations",
    icon: Link2,
    activeColor: "text-orange-400",
  },
] as const;

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  };

  const isActive = (href: string) => {
    if (href === "/chat") {
      return (
        pathname === "/chat" ||
        (pathname.startsWith("/chat/") &&
          !pathname.startsWith("/chat/memories") &&
          !pathname.startsWith("/chat/documents") &&
          !pathname.startsWith("/chat/transactions") &&
          !pathname.startsWith("/chat/workflows") &&
          !pathname.startsWith("/chat/skills") &&
          !pathname.startsWith("/chat/integrations"))
      );
    }
    return pathname.startsWith(href);
  };

  return (
    <>
      {/* Desktop: vertical sidebar nav */}
      <nav className="hidden md:flex w-[72px] shrink-0 flex-col items-center bg-zinc-50 dark:bg-zinc-900 border-r border-zinc-200 dark:border-zinc-800 py-3">
        {/* Top nav items */}
        <div className="flex flex-1 flex-col items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            return (
              <button
                key={item.href}
                onClick={() => router.push(item.href)}
                className={`group relative flex flex-col items-center justify-center w-14 h-14 rounded-xl transition-colors ${
                  active
                    ? "bg-zinc-200 dark:bg-zinc-800 " + item.activeColor
                    : "text-zinc-500 hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 hover:text-zinc-700 dark:hover:text-zinc-300"
                }`}
                title={item.label}
              >
                <Icon size={20} />
                <span className="mt-1 text-[10px] font-medium leading-none">
                  {item.label}
                </span>
              </button>
            );
          })}
        </div>

        {/* Bottom actions */}
        <div className="flex flex-col items-center gap-1 pt-2 border-t border-zinc-200 dark:border-zinc-800">
          <ThemeToggle />
          <button
            onClick={handleLogout}
            className="flex items-center justify-center w-10 h-10 rounded-lg text-zinc-500 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-zinc-700 dark:hover:text-zinc-300"
            title="Log out"
          >
            <LogOut size={18} />
          </button>
        </div>
      </nav>

      {/* Mobile: bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around bg-zinc-50 dark:bg-zinc-900 border-t border-zinc-200 dark:border-zinc-800 px-2 py-1 safe-area-pb">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href);
          const Icon = item.icon;
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={`flex flex-col items-center justify-center py-2 px-3 rounded-lg transition-colors ${
                active
                  ? item.activeColor
                  : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
              }`}
            >
              <Icon size={20} />
              <span className="mt-0.5 text-[10px] font-medium">
                {item.label}
              </span>
            </button>
          );
        })}
        <button
          onClick={handleLogout}
          className="flex flex-col items-center justify-center py-2 px-3 rounded-lg text-zinc-500 transition-colors hover:text-zinc-700 dark:hover:text-zinc-300"
        >
          <LogOut size={20} />
          <span className="mt-0.5 text-[10px] font-medium">Logout</span>
        </button>
      </nav>
    </>
  );
}
