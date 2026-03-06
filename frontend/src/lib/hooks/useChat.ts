"use client";

import { useState, useCallback, useRef } from "react";
import type {
  Message,
  StreamingMessage,
  ToolCall,
  SourceReference,
  PendingToolApproval,
} from "@/types";
import { sendMessage, fetchConversation, approveToolCalls } from "@/lib/api";
import { logger } from "@/lib/logger";

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
  const [pendingApproval, setPendingApproval] =
    useState<PendingToolApproval | null>(null);
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
        logger.error("chat_load_messages_failed", {
          conversationId: id,
          error: err instanceof Error ? err.message : String(err),
        });
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
        pendingApproval: null,
      });

      try {
        logger.info("chat_send_start", { conversationId });
        const response = await sendMessage(conversationId, text);
        if (!response.ok) {
          logger.warn("chat_send_http_error", {
            conversationId,
            status: response.status,
          });
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
                  case "tool_approval_needed": {
                    const approval: PendingToolApproval = {
                      conversationId: parsed.conversation_id as string,
                      toolCalls: (parsed.tool_calls ?? []) as PendingToolApproval["toolCalls"],
                    };
                    setPendingApproval(approval);
                    setStreamingMessage((prev) =>
                      prev
                        ? {
                            ...prev,
                            isStreaming: false,
                            pendingApproval: approval,
                          }
                        : null
                    );
                    break;
                  }
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
              } catch (err) {
                logger.warn("chat_stream_parse_error", {
                  conversationId,
                  eventType,
                  error: err instanceof Error ? err.message : String(err),
                });
              }
              // Reset eventType after processing data
              eventType = "";
            }
            // Empty lines (SSE delimiter) are ignored
          }
        }
      } catch (err) {
        logger.error("chat_send_failed", {
          conversationId,
          error: err instanceof Error ? err.message : String(err),
        });
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

  const resolveApproval = useCallback(
    async (approved: boolean) => {
      if (!pendingApproval || !conversationId) return;

      const toolCallIds = pendingApproval.toolCalls.map((tc) => tc.id);
      setPendingApproval(null);
      setIsLoading(true);
      setStreamingMessage({
        role: "assistant",
        content: "",
        thinking: "",
        toolCalls: null,
        sources: null,
        isStreaming: true,
        pendingApproval: null,
      });

      try {
        logger.info("chat_approval_start", {
          conversationId,
          approved,
          toolCallCount: toolCallIds.length,
        });
        const response = await approveToolCalls(
          conversationId,
          toolCallIds,
          approved
        );
        if (!response.ok) {
          logger.warn("chat_approval_http_error", {
            conversationId,
            status: response.status,
          });
          throw new Error("Approval request failed");
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";
        let eventType = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n");
          buffer = parts.pop() || "";

          for (const line of parts) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
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
                  case "tool_approval_needed": {
                    const approval2: PendingToolApproval = {
                      conversationId: parsed.conversation_id as string,
                      toolCalls: (parsed.tool_calls ?? []) as PendingToolApproval["toolCalls"],
                    };
                    setPendingApproval(approval2);
                    setStreamingMessage((prev) =>
                      prev
                        ? {
                            ...prev,
                            isStreaming: false,
                            pendingApproval: approval2,
                          }
                        : null
                    );
                    break;
                  }
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
              } catch (err) {
                logger.warn("chat_approval_stream_parse_error", {
                  conversationId,
                  eventType,
                  error: err instanceof Error ? err.message : String(err),
                });
              }
              eventType = "";
            }
          }
        }
      } catch (err) {
        logger.error("chat_approval_failed", {
          conversationId,
          error: err instanceof Error ? err.message : String(err),
        });
        setError(
          err instanceof Error ? err.message : "Failed to process approval"
        );
      } finally {
        setStreamingMessage(null);
        setIsLoading(false);
        await loadMessages();
      }
    },
    [pendingApproval, conversationId, loadMessages]
  );

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
    setStreamingMessage(null);
    setIsLoading(false);
    setPendingApproval(null);
  }, []);

  return {
    messages,
    streamingMessage,
    isLoading,
    error,
    pendingApproval,
    send,
    resolveApproval,
    cancel,
    loadMessages,
    setMessages,
  };
}
