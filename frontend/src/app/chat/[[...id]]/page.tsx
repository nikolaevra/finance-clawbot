"use client";

import { useEffect, useCallback } from "react";
import ChatArea from "@/components/ChatArea";
import { useChat } from "@/lib/hooks/useChat";
import { useConversations } from "@/components/ConversationProvider";

export default function ChatPage() {
  const { activeConversationId, activeConversation, updateConversationTitle } =
    useConversations();

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
