import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchConversations: vi.fn(),
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  fetchConversation: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  fetchConversations: mocks.fetchConversations,
  createConversation: mocks.createConversation,
  deleteConversation: mocks.deleteConversation,
  fetchConversation: mocks.fetchConversation,
}));

import ConversationProvider, { useConversations } from "./ConversationProvider";

function ProviderConsumer() {
  const { conversations, activeConversationId, createChat, deleteChat } =
    useConversations();
  return (
    <div>
      <div data-testid="count">{conversations.length}</div>
      <div data-testid="active">{activeConversationId ?? "none"}</div>
      <button
        onClick={async () => {
          await createChat();
        }}
      >
        create
      </button>
      <button
        onClick={async () => {
          if (activeConversationId) {
            await deleteChat(activeConversationId);
          }
        }}
      >
        delete-active
      </button>
    </div>
  );
}

describe("ConversationProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchConversation.mockResolvedValue({
      id: "conv-1",
      user_id: "user-1",
      title: "New Chat",
      created_at: "2026-03-08T00:00:00.000Z",
      updated_at: "2026-03-08T00:00:00.000Z",
      messages: [],
    });
  });

  it("does not auto-create conversation when list is empty", async () => {
    mocks.fetchConversations.mockResolvedValue([]);

    render(
      <ConversationProvider>
        <ProviderConsumer />
      </ConversationProvider>
    );

    await waitFor(() => expect(mocks.fetchConversations).toHaveBeenCalled());
    expect(mocks.createConversation).not.toHaveBeenCalled();
    expect(screen.getByTestId("count")).toHaveTextContent("0");
    expect(screen.getByTestId("active")).toHaveTextContent("none");
  });

  it("creates chat on demand and selects it", async () => {
    mocks.fetchConversations.mockResolvedValue([]);
    mocks.createConversation.mockResolvedValue({
      id: "conv-new",
      user_id: "user-1",
      title: "New Chat",
      created_at: "2026-03-08T00:00:00.000Z",
      updated_at: "2026-03-08T00:00:00.000Z",
      messages: [],
    });

    render(
      <ConversationProvider>
        <ProviderConsumer />
      </ConversationProvider>
    );

    fireEvent.click(screen.getByText("create"));
    await waitFor(() =>
      expect(mocks.createConversation).toHaveBeenCalledWith("New Chat")
    );
    await waitFor(() =>
      expect(screen.getByTestId("active")).toHaveTextContent("conv-new")
    );
    expect(screen.getByTestId("count")).toHaveTextContent("1");
  });

  it("deleting last active chat leaves no active conversation", async () => {
    mocks.fetchConversations.mockResolvedValue([
      {
        id: "conv-1",
        user_id: "user-1",
        title: "Only chat",
        created_at: "2026-03-08T00:00:00.000Z",
        updated_at: "2026-03-08T00:00:00.000Z",
        messages: [],
      },
    ]);
    mocks.deleteConversation.mockResolvedValue(undefined);

    render(
      <ConversationProvider>
        <ProviderConsumer />
      </ConversationProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("active")).toHaveTextContent("conv-1")
    );
    fireEvent.click(screen.getByText("delete-active"));

    await waitFor(() =>
      expect(mocks.deleteConversation).toHaveBeenCalledWith("conv-1")
    );
    await waitFor(() =>
      expect(screen.getByTestId("active")).toHaveTextContent("none")
    );
    expect(screen.getByTestId("count")).toHaveTextContent("0");
    expect(mocks.createConversation).not.toHaveBeenCalled();
  });
});
