"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type { Conversation } from "@/types";
import {
  fetchConversations,
  createConversation,
  deleteConversation as apiDeleteConversation,
  fetchConversation,
} from "@/lib/api";

interface ConversationContextValue {
  conversations: Conversation[];
  activeConversationId: string | null;
  activeConversation: Conversation | null;
  isSidebarOpen: boolean;
  isMobileSidebarOpen: boolean;
  setActiveConversationId: (id: string) => void;
  createChat: () => Promise<void>;
  deleteChat: (id: string) => Promise<void>;
  refreshConversations: () => Promise<Conversation[]>;
  updateConversationTitle: (id: string, title: string) => void;
  toggleSidebar: () => void;
  toggleMobileSidebar: () => void;
}

const ConversationContext = createContext<ConversationContextValue | null>(null);

export function useConversations() {
  const ctx = useContext(ConversationContext);
  if (!ctx)
    throw new Error("useConversations must be used within ConversationProvider");
  return ctx;
}

export default function ConversationProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [activeConversation, setActiveConversation] =
    useState<Conversation | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [initialized, setInitialized] = useState(false);

  const refreshConversations = useCallback(async () => {
    try {
      const convos = await fetchConversations();
      setConversations(convos);
      return convos;
    } catch {
      return [] as Conversation[];
    }
  }, []);

  // Initial load: fetch conversations, select most recent or create one
  useEffect(() => {
    if (initialized) return;
    let cancelled = false;

    async function init() {
      const convos = await refreshConversations();
      if (cancelled) return;

      if (convos.length > 0) {
        setActiveConversationId(convos[0].id);
      } else {
        try {
          const newConv = await createConversation("New Chat");
          if (cancelled) return;
          setConversations([newConv]);
          setActiveConversationId(newConv.id);
        } catch {
          // will retry on next interaction
        }
      }
      setInitialized(true);
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [initialized, refreshConversations]);

  // When active conversation changes, load its messages
  useEffect(() => {
    if (!activeConversationId) {
      setActiveConversation(null);
      return;
    }

    let cancelled = false;
    async function load() {
      try {
        const conv = await fetchConversation(activeConversationId!);
        if (!cancelled) setActiveConversation(conv);
      } catch {
        if (!cancelled) setActiveConversation(null);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [activeConversationId]);

  const createChat = useCallback(async () => {
    try {
      const newConv = await createConversation("New Chat");
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
    } catch {
      // handled by error boundaries or retry
    }
  }, []);

  const deleteChat = useCallback(
    async (id: string) => {
      try {
        await apiDeleteConversation(id);
        setConversations((prev) => {
          const remaining = prev.filter((c) => c.id !== id);

          if (activeConversationId === id) {
            if (remaining.length > 0) {
              setActiveConversationId(remaining[0].id);
            } else {
              // Create a new chat since we deleted the last one
              createConversation("New Chat").then((newConv) => {
                setConversations([newConv]);
                setActiveConversationId(newConv.id);
              });
            }
          }

          return remaining;
        });
      } catch {
        // handled by error boundaries or retry
      }
    },
    [activeConversationId]
  );

  const updateConversationTitle = useCallback(
    (id: string, title: string) => {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title } : c))
      );
      if (activeConversation && activeConversation.id === id) {
        setActiveConversation((prev) => (prev ? { ...prev, title } : prev));
      }
    },
    [activeConversation]
  );

  const toggleSidebar = useCallback(() => {
    setIsSidebarOpen((prev) => !prev);
  }, []);

  const toggleMobileSidebar = useCallback(() => {
    setIsMobileSidebarOpen((prev) => !prev);
  }, []);

  return (
    <ConversationContext.Provider
      value={{
        conversations,
        activeConversationId,
        activeConversation,
        isSidebarOpen,
        isMobileSidebarOpen,
        setActiveConversationId,
        createChat,
        deleteChat,
        refreshConversations,
        updateConversationTitle,
        toggleSidebar,
        toggleMobileSidebar,
      }}
    >
      {children}
    </ConversationContext.Provider>
  );
}
