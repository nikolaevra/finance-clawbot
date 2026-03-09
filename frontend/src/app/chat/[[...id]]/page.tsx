"use client";

import { useEffect, useCallback, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import ChatArea from "@/components/ChatArea";
import { useChat } from "@/lib/hooks/useChat";
import { useConversations } from "@/components/ConversationProvider";

export default function ChatPage() {
  const {
    activeConversationId,
    activeConversation,
    setActiveConversationId,
    updateConversationTitle,
  } = useConversations();
  const params = useParams<{ id?: string[] }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const autoSentRef = useRef<string | null>(null);
  const routeConversationId = params?.id?.[0] ?? null;
  const queryPrompt = (searchParams.get("q") || "").trim();

  const {
    messages,
    streamingMessage,
    isLoading,
    error,
    pendingApproval,
    send,
    resolveApproval,
    setMessages,
  } = useChat({
    conversationId: activeConversationId,
    onTitleUpdate: useCallback(
      (title: string) => {
        if (activeConversationId) {
          updateConversationTitle(activeConversationId, title);
        }
      },
      [activeConversationId, updateConversationTitle]
    ),
  });

  // When active conversation changes, load its messages
  useEffect(() => {
    if (activeConversation) {
      setMessages(activeConversation.messages || []);
    } else {
      setMessages([]);
    }
  }, [activeConversation, setMessages]);

  // Keep provider state in sync with route state for /chat/<conversationId>.
  useEffect(() => {
    if (!routeConversationId) return;
    if (activeConversationId === routeConversationId) return;
    setActiveConversationId(routeConversationId);
  }, [routeConversationId, activeConversationId, setActiveConversationId]);

  // Auto-send initial prompt from /chat/<id>?q=... once, then normalize URL.
  useEffect(() => {
    if (!routeConversationId || !queryPrompt) return;
    if (activeConversationId !== routeConversationId) return;
    if (isLoading) return;

    const promptKey = `${routeConversationId}:${queryPrompt}`;
    if (autoSentRef.current === promptKey) return;

    autoSentRef.current = promptKey;
    void send(queryPrompt);
    router.replace(`/chat/${routeConversationId}`);
  }, [
    routeConversationId,
    queryPrompt,
    activeConversationId,
    isLoading,
    send,
    router,
  ]);

  const handleSend = useCallback(
    (message: string) => {
      send(message);
    },
    [send]
  );

  return (
    <>
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-900/50 px-4 py-2 text-center text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}
      <ChatArea
        messages={messages}
        streamingMessage={streamingMessage}
        onSend={handleSend}
        isLoading={isLoading}
        pendingApproval={pendingApproval}
        onResolveApproval={resolveApproval}
        conversationId={activeConversationId}
      />
    </>
  );
}
