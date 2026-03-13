"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  Trash2,
  PanelLeftClose,
  PanelLeft,
  X,
  Menu,
} from "lucide-react";
import { useConversations } from "./ConversationProvider";

function formatRelativeTime(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHr = Math.floor(diffMs / 3_600_000);
  const diffDay = Math.floor(diffMs / 86_400_000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function ChatSidebarToggle() {
  const { isSidebarOpen, toggleSidebar } = useConversations();

  if (isSidebarOpen) return null;

  return (
    <div className="hidden md:flex items-center px-3 py-2">
      <button
        onClick={toggleSidebar}
        className="flex items-center justify-center w-8 h-8 rounded-lg text-foreground/30 hover:text-foreground/60 hover:bg-foreground/[0.06]"
        title="Open sidebar"
      >
        <PanelLeft size={16} strokeWidth={1.5} />
      </button>
    </div>
  );
}

export function MobileChatSidebarToggle() {
  const { toggleMobileSidebar } = useConversations();

  return (
    <button
      onClick={toggleMobileSidebar}
      className="md:hidden fixed top-3 left-3 z-40 flex items-center justify-center w-9 h-9 rounded-md glass bg-foreground/[0.1] text-foreground/70 shadow-lg shadow-black/25 border border-foreground/[0.14]"
      title="Open chats"
    >
      <Menu size={16} strokeWidth={1.5} />
    </button>
  );
}

function ConversationList({
  onSelectMobile,
  showCollapseToggle,
}: {
  onSelectMobile?: () => void;
  showCollapseToggle?: boolean;
}) {
  const {
    conversations,
    activeConversationId,
    setActiveConversationId,
    createChat,
    deleteChat,
    toggleSidebar,
  } = useConversations();
  const router = useRouter();

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleSelect = (id: string) => {
    setActiveConversationId(id);
    router.push(`/chat/${id}`);
    onSelectMobile?.();
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setDeletingId(id);
    await deleteChat(id);
    setDeletingId(null);
  };

  const handleCreate = async () => {
    const newConversationId = await createChat();
    if (newConversationId) {
      router.push(`/chat/${newConversationId}`);
    }
    onSelectMobile?.();
  };

  return (
    <>
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2">
          {showCollapseToggle && (
            <button
              onClick={toggleSidebar}
              className="flex items-center justify-center w-7 h-7 rounded-lg text-foreground/30 hover:text-foreground/60 hover:bg-foreground/[0.06]"
              title="Collapse sidebar"
            >
              <PanelLeftClose size={14} strokeWidth={1.5} />
            </button>
          )}
          <h2 className="text-[13px] font-medium text-foreground/50 tracking-wide uppercase">
            Chats
          </h2>
        </div>
        <button
          onClick={handleCreate}
          className="flex items-center gap-1.5 rounded-lg border border-foreground/[0.1] px-2.5 py-1.5 text-xs font-medium text-foreground/60 hover:text-foreground/90 hover:bg-foreground/[0.06] hover:border-foreground/[0.15]"
          title="New chat"
        >
          <Plus size={13} strokeWidth={1.5} />
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-1">
        {conversations.length === 0 && (
          <p className="px-3 py-10 text-center text-xs text-foreground/25">
            No conversations yet
          </p>
        )}

        {conversations.map((conv) => {
          const isActive = conv.id === activeConversationId;
          const isDeleting = conv.id === deletingId;
          const isBackground =
            conv.agent_mode === "background" ||
            conv.conversation_type === "background";
          const agentBadge = isBackground ? "Background" : "Live";
          const sourceMeta = isBackground
            ? [conv.agent_name, conv.agent_source].filter(Boolean).join(" · ")
            : "";

          return (
            <div
              key={conv.id}
              role="button"
              tabIndex={0}
              onClick={() => !isDeleting && handleSelect(conv.id)}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && !isDeleting) {
                  e.preventDefault();
                  handleSelect(conv.id);
                }
              }}
              className={`group relative flex w-full items-start gap-2 rounded-md border border-transparent px-3 py-2.5 text-left transition-all duration-150 cursor-pointer ${
                isActive
                  ? "border-foreground/20 bg-foreground/[0.14]"
                  : "hover:bg-foreground/[0.08]"
              } ${isDeleting ? "opacity-40 pointer-events-none" : ""}`}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-sm bg-blue-500" />
              )}
              <div className="flex-1 min-w-0 pr-5">
                <p
                  className={`truncate text-[13px] leading-snug ${
                    isActive
                      ? "font-medium text-foreground"
                      : "text-foreground/75"
                  }`}
                >
                  {conv.title}
                </p>
                <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5">
                  <span
                    className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
                      isBackground
                        ? "bg-violet-500/20 text-violet-200 ring-1 ring-violet-400/40"
                        : "bg-blue-500/20 text-blue-200 ring-1 ring-blue-400/40"
                    }`}
                  >
                    {agentBadge}
                  </span>
                  {sourceMeta && (
                    <span className="min-w-0 truncate text-[10px] text-foreground/50">
                      {sourceMeta}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[11px] text-foreground/45">
                  {formatRelativeTime(conv.updated_at)}
                </p>
              </div>

              <button
                onClick={(e) => handleDelete(e, conv.id)}
                disabled={isDeleting}
                className="absolute right-2 top-1/2 -translate-y-1/2 flex h-6 w-6 items-center justify-center rounded-md opacity-0 group-hover:opacity-100 text-foreground/30 hover:text-red-400 hover:bg-red-400/10"
                title="Delete chat"
              >
                <Trash2 size={12} strokeWidth={1.5} />
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

export function MobileChatSidebar() {
  const { isMobileSidebarOpen, toggleMobileSidebar } = useConversations();

  if (!isMobileSidebarOpen) return null;

  return (
    <div className="md:hidden fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={toggleMobileSidebar}
      />
      <aside className="absolute inset-y-0 left-0 flex w-[280px] flex-col glass bg-background/95 shadow-2xl shadow-black/40 border-r border-foreground/[0.14]">
        <div className="flex items-center justify-end px-3 pt-3">
          <button
            onClick={toggleMobileSidebar}
            className="flex items-center justify-center w-8 h-8 rounded-lg text-foreground/30 hover:text-foreground/60 hover:bg-foreground/[0.06]"
            title="Close"
          >
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
        <ConversationList onSelectMobile={toggleMobileSidebar} />
      </aside>
    </div>
  );
}

export default function ChatSidebar() {
  const { isSidebarOpen } = useConversations();

  if (!isSidebarOpen) return null;

  return (
    <aside className="hidden md:flex w-[260px] shrink-0 flex-col bg-foreground/[0.04] border-r border-foreground/[0.1]">
      <ConversationList showCollapseToggle />
    </aside>
  );
}
