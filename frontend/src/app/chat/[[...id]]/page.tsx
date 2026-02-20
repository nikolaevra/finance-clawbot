"use client";

import { useEffect, useState, useCallback } from "react";
import ChatArea from "@/components/ChatArea";
import { useChat } from "@/lib/hooks/useChat";
import { fetchCurrentConversation } from "@/lib/api";

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);

  const {
    messages,
    streamingMessage,
    isLoading,
    error,
    send,
    setMessages,
  } = useChat({
    conversationId,
  });

  // On mount, load the single conversation (get-or-create)
  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const conv = await fetchCurrentConversation();
        if (cancelled) return;
        setConversationId(conv.id);
        setMessages(conv.messages || []);
      } catch {
        // Will be handled by error state in useChat or retry
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [setMessages]);

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
      />
    </>
  );
}
