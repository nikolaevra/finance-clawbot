"use client";

import { useState, useCallback, useRef } from "react";
import type { Message, StreamingMessage, ToolCall, SourceReference } from "@/types";
import { sendMessage, fetchConversation } from "@/lib/api";

interface UseChatOptions {
  conversationId: string | null;
  onTitleUpdate?: (title: string) => void;
}

export function useChat({ conversationId, onTitleUpdate }: UseChatOptions) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingMessage, setStreamingMessage] =
    useState<StreamingMessage | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const onTitleUpdateRef = useRef(onTitleUpdate);
  onTitleUpdateRef.current = onTitleUpdate;

  const loadMessages = useCallback(
    async (convId?: string) => {
      const id = convId || conversationId;
      if (!id) return;

      try {
        const data = await fetchConversation(id);
        setMessages(data.messages || []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load messages"
        );
      }
    },
    [conversationId]
  );

  const send = useCallback(
    async (text: string) => {
      if (!conversationId || isLoading) return;

      setError(null);
      setIsLoading(true);

      // Optimistically add user message to UI
      const tempUserMsg: Message = {
        id: `temp-${Date.now()}`,
        conversation_id: conversationId,
        role: "user",
        content: text,
        tool_calls: null,
        tool_call_id: null,
        model: null,
        thinking: null,
        sources: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, tempUserMsg]);

      // Start streaming assistant message
      setStreamingMessage({
        role: "assistant",
        content: "",
        thinking: "",
        toolCalls: null,
        sources: null,
        isStreaming: true,
      });

      try {
        const response = await sendMessage(conversationId, text);
        if (!response.ok) {
          throw new Error("Chat request failed");
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";
        // Keep eventType across chunks so split events aren't lost
        let eventType = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete SSE events (delimited by double newlines)
          const parts = buffer.split("\n");
          buffer = parts.pop() || "";

          for (const line of parts) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                // Inline event handling to avoid stale closure issues
                switch (eventType) {
                  case "thinking":
                    setStreamingMessage((prev) =>
                      prev
                        ? {
                            ...prev,
                            thinking:
                              prev.thinking + (parsed.content as string),
                          }
                        : null
                    );
                    break;
                  case "content":
                    setStreamingMessage((prev) =>
                      prev
                        ? {
                            ...prev,
                            content:
                              prev.content + (parsed.content as string),
                          }
                        : null
                    );
                    break;
                  case "tool_call":
                    setStreamingMessage((prev) => {
                      if (!prev) return null;
                      const tc = parsed.tool_call as ToolCall;
                      const existing = prev.toolCalls
                        ? [...prev.toolCalls]
                        : [];
                      const idx = parsed.index as number;
                      existing[idx] = tc;
                      return { ...prev, toolCalls: existing };
                    });
                    break;
                  case "sources":
                    setStreamingMessage((prev) =>
                      prev
                        ? {
                            ...prev,
                            sources: parsed.sources as SourceReference[],
                          }
                        : null
                    );
                    break;
                  case "title":
                    if (
                      onTitleUpdateRef.current &&
                      typeof parsed.title === "string"
                    ) {
                      onTitleUpdateRef.current(parsed.title);
                    }
                    break;
                  case "done":
                    setStreamingMessage((prev) =>
                      prev ? { ...prev, isStreaming: false } : null
                    );
                    break;
                  case "error":
                    setError(
                      typeof parsed.error === "string"
                        ? parsed.error
                        : "Stream error"
                    );
                    setStreamingMessage(null);
                    break;
                }
              } catch {
                // Ignore JSON parse errors
              }
              // Reset eventType after processing data
              eventType = "";
            }
            // Empty lines (SSE delimiter) are ignored
          }
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to send message"
        );
      } finally {
        // Finalize: clear streaming message and reload from DB
        setStreamingMessage(null);
        setIsLoading(false);
        await loadMessages();
      }
    },
    [conversationId, isLoading, loadMessages]
  );

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
    setStreamingMessage(null);
    setIsLoading(false);
  }, []);

  return {
    messages,
    streamingMessage,
    isLoading,
    error,
    send,
    cancel,
    loadMessages,
    setMessages,
  };
}
