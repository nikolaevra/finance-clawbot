import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  setActiveConversationId: vi.fn(),
  createChat: vi.fn(),
  deleteChat: vi.fn(),
  toggleSidebar: vi.fn(),
  toggleMobileSidebar: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
  }),
}));

vi.mock("./ConversationProvider", () => ({
  useConversations: () => ({
    conversations: [
      {
        id: "conv-1",
        user_id: "user-1",
        title: "First chat",
        created_at: "2026-03-08T00:00:00.000Z",
        updated_at: "2026-03-08T00:00:00.000Z",
      },
    ],
    activeConversationId: "conv-1",
    activeConversation: null,
    isSidebarOpen: true,
    isMobileSidebarOpen: false,
    setActiveConversationId: mocks.setActiveConversationId,
    createChat: mocks.createChat,
    deleteChat: mocks.deleteChat,
    refreshConversations: vi.fn(),
    updateConversationTitle: vi.fn(),
    toggleSidebar: mocks.toggleSidebar,
    toggleMobileSidebar: mocks.toggleMobileSidebar,
  }),
}));

import ChatSidebar from "./ChatSidebar";

describe("ChatSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createChat.mockResolvedValue("conv-new");
  });

  it("navigates to selected conversation route", () => {
    render(<ChatSidebar />);
    fireEvent.click(screen.getByText("First chat"));

    expect(mocks.setActiveConversationId).toHaveBeenCalledWith("conv-1");
    expect(mocks.push).toHaveBeenCalledWith("/chat/conv-1");
  });

  it("creates a chat and navigates to new route", async () => {
    render(<ChatSidebar />);
    fireEvent.click(screen.getByRole("button", { name: "New" }));

    await waitFor(() => expect(mocks.createChat).toHaveBeenCalled());
    expect(mocks.push).toHaveBeenCalledWith("/chat/conv-new");
  });

  it("does not navigate when chat creation returns null", async () => {
    mocks.createChat.mockResolvedValue(null);
    render(<ChatSidebar />);
    fireEvent.click(screen.getByRole("button", { name: "New" }));

    await waitFor(() => expect(mocks.createChat).toHaveBeenCalled());
    expect(mocks.push).not.toHaveBeenCalledWith("/chat/conv-new");
  });
});
