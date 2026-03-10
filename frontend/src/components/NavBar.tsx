"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  Brain,
  House,
  MessageSquare,
  FileText,
  Link2,
  LogOut,
  Sparkles,
} from "lucide-react";
import { createClient } from "@/lib/supabase";
import ThemeToggle from "./ThemeToggle";

const NAV_ITEMS = [
  { label: "Home", href: "/", icon: House },
  { label: "Chat", href: "/chat", icon: MessageSquare },
  { label: "Memories", href: "/chat/memories", icon: Brain },
  { label: "Documents", href: "/chat/documents", icon: FileText },
  { label: "Automations", href: "/chat/automations", icon: Sparkles },
  { label: "Integrations", href: "/chat/integrations", icon: Link2 },
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
    if (href === "/") return pathname === "/";
    if (href === "/chat") {
      return (
        pathname === "/chat" ||
        (pathname.startsWith("/chat/") &&
          !pathname.startsWith("/chat/memories") &&
          !pathname.startsWith("/chat/documents") &&
          !pathname.startsWith("/chat/skills") &&
          !pathname.startsWith("/chat/automations") &&
          !pathname.startsWith("/chat/integrations"))
      );
    }
    if (href === "/chat/automations") {
      return (
        pathname.startsWith("/chat/automations") ||
        pathname.startsWith("/chat/skills")
      );
    }
    return pathname.startsWith(href);
  };

  return (
    <>
      {/* Desktop: icon-only vertical nav */}
      <nav className="hidden md:flex w-16 shrink-0 flex-col items-center glass bg-foreground/[0.03] dark:bg-foreground/[0.03] border-r border-foreground/[0.06] py-4">
        <div className="flex flex-1 flex-col items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            return (
              <button
                key={item.href}
                onClick={() => router.push(item.href)}
                className={`group relative flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 ${
                  active
                    ? "bg-foreground/10 text-foreground"
                    : "text-foreground/40 hover:text-foreground/70 hover:bg-foreground/[0.06]"
                }`}
                title={item.label}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-[3px] w-[3px] h-5 rounded-full bg-blue-400" />
                )}
                <Icon size={18} strokeWidth={active ? 2 : 1.5} />
              </button>
            );
          })}
        </div>

        <div className="flex flex-col items-center gap-1 pt-3">
          <ThemeToggle />
          <button
            onClick={handleLogout}
            className="flex items-center justify-center w-10 h-10 rounded-xl text-foreground/30 hover:text-foreground/60 hover:bg-foreground/[0.06]"
            title="Log out"
          >
            <LogOut size={16} strokeWidth={1.5} />
          </button>
        </div>
      </nav>

      {/* Mobile: frosted bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around glass bg-black/60 dark:bg-black/70 border-t border-foreground/[0.08] px-2 py-2 safe-area-pb">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href);
          const Icon = item.icon;
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={`flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 ${
                active
                  ? "text-blue-400 bg-blue-400/10"
                  : "text-foreground/40 hover:text-foreground/60"
              }`}
            >
              <Icon size={20} strokeWidth={active ? 2 : 1.5} />
            </button>
          );
        })}
        <button
          onClick={handleLogout}
          className="flex items-center justify-center w-10 h-10 rounded-xl text-foreground/40 hover:text-foreground/60"
        >
          <LogOut size={20} strokeWidth={1.5} />
        </button>
      </nav>
    </>
  );
}
