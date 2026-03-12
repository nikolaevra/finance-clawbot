"use client";

import type { Message, StreamingMessage, PendingToolApproval, PendingExternalWait } from "@/types";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";

interface ChatAreaProps {
  messages: Message[];
  streamingMessage: StreamingMessage | null;
  onSend: (message: string) => void;
  isLoading: boolean;
  pendingApproval?: PendingToolApproval | null;
  pendingExternalWait?: PendingExternalWait | null;
  onResolveApproval?: (approved: boolean) => void;
  conversationId?: string | null;
}

export default function ChatArea({
  messages, streamingMessage, onSend, isLoading, pendingApproval, pendingExternalWait, onResolveApproval, conversationId,
}: ChatAreaProps) {
  return (
    <div className="flex flex-1 flex-col min-h-0">
      <MessageList
        messages={messages}
        streamingMessage={streamingMessage}
        pendingApproval={pendingApproval}
        pendingExternalWait={pendingExternalWait}
        onResolveApproval={onResolveApproval}
        conversationId={conversationId}
      />
      <MessageInput onSend={onSend} disabled={isLoading} />
    </div>
  );
}
