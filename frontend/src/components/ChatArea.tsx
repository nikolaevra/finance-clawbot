"use client";

import type { Message, StreamingMessage } from "@/types";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";

interface ChatAreaProps {
  messages: Message[];
  streamingMessage: StreamingMessage | null;
  onSend: (message: string) => void;
  isLoading: boolean;
}

export default function ChatArea({
  messages,
  streamingMessage,
  onSend,
  isLoading,
}: ChatAreaProps) {
  return (
    <div className="flex flex-1 flex-col min-h-0 bg-white dark:bg-zinc-950">
      <MessageList messages={messages} streamingMessage={streamingMessage} />
      <MessageInput onSend={onSend} disabled={isLoading} />
    </div>
  );
}
