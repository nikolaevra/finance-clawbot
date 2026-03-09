import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createConversation: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
  }),
}));

vi.mock("@/lib/api", () => ({
  createConversation: mocks.createConversation,
}));

import StarterHome from "./StarterHome";

describe("StarterHome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createConversation.mockResolvedValue({ id: "conv-123" });
  });

  it("creates a conversation and routes to chat with first prompt", async () => {
    render(<StarterHome userName="Sarah Connor" />);

    fireEvent.change(
      screen.getByPlaceholderText("Ask your Finance AI Assistant anything..."),
      {
        target: { value: "Draft a project kickoff plan" },
      }
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() =>
      expect(mocks.createConversation).toHaveBeenCalledWith("New Chat")
    );
    expect(mocks.push).toHaveBeenCalledWith(
      "/chat/conv-123?q=Draft+a+project+kickoff+plan"
    );
  });

  it("shows an error if conversation creation fails", async () => {
    mocks.createConversation.mockRejectedValue(new Error("boom"));
    render(<StarterHome />);

    fireEvent.change(
      screen.getByPlaceholderText("Ask your Finance AI Assistant anything..."),
      {
        target: { value: "Hello" },
      }
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText("Unable to start a new conversation. Please try again.")
    ).toBeInTheDocument();
  });

  it("shows finance assistant greeting", () => {
    render(<StarterHome userName="Alex Rivera" />);
    expect(screen.getByText(/Finance AI Assistant/i)).toBeInTheDocument();
    expect(screen.getByText(/Good .*Alex/i)).toBeInTheDocument();
  });
});
