import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useParams: vi.fn(),
  useSearchParams: vi.fn(),
  replace: vi.fn(),
  setActiveConversationId: vi.fn(),
  updateConversationTitle: vi.fn(),
  send: vi.fn(),
  resolveApproval: vi.fn(),
  setMessages: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: mocks.useParams,
  useSearchParams: mocks.useSearchParams,
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@/components/ConversationProvider", () => ({
  useConversations: () => ({
    activeConversationId: "conv-1",
    activeConversation: null,
    setActiveConversationId: mocks.setActiveConversationId,
    updateConversationTitle: mocks.updateConversationTitle,
  }),
}));

vi.mock("@/lib/hooks/useChat", () => ({
  useChat: () => ({
    messages: [],
    streamingMessage: null,
    isLoading: false,
    error: null,
    pendingApproval: null,
    send: mocks.send,
    resolveApproval: mocks.resolveApproval,
    setMessages: mocks.setMessages,
  }),
}));

vi.mock("@/components/ChatArea", () => ({
  default: () => <div data-testid="chat-area" />,
}));

import ChatPage from "./page";

describe("ChatPage route sync", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useParams.mockReturnValue({ id: ["conv-1"] });
    mocks.useSearchParams.mockReturnValue({
      get: (key: string) => (key === "q" ? "hello from home" : null),
    });
  });

  it("auto-sends initial query prompt and normalizes URL", async () => {
    render(<ChatPage />);

    await waitFor(() =>
      expect(mocks.send).toHaveBeenCalledWith("hello from home")
    );
    expect(mocks.replace).toHaveBeenCalledWith("/chat/conv-1");
  });

  it("syncs active conversation from route when different", async () => {
    mocks.useParams.mockReturnValue({ id: ["conv-2"] });
    render(<ChatPage />);

    await waitFor(() =>
      expect(mocks.setActiveConversationId).toHaveBeenCalledWith("conv-2")
    );
  });
});
