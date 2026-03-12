import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createConversation: vi.fn(),
  fetchInboxThreads: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
  }),
}));

vi.mock("@/lib/api", () => ({
  createConversation: mocks.createConversation,
  fetchInboxThreads: mocks.fetchInboxThreads,
}));

import StarterHome from "./StarterHome";

describe("StarterHome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createConversation.mockResolvedValue({ id: "conv-123" });
    mocks.fetchInboxThreads.mockResolvedValue({ threads: [], page: 1, limit: 10, has_more: false });
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

  it("shows finance assistant greeting", async () => {
    render(<StarterHome userName="Alex Rivera" />);
    expect(screen.getByText(/Finance AI Assistant/i)).toBeInTheDocument();
    expect(screen.getByText(/Good .*Alex/i)).toBeInTheDocument();
    await waitFor(() => expect(mocks.fetchInboxThreads).toHaveBeenCalled());
  });

  it("renders AI thread summary preview when available", async () => {
    mocks.fetchInboxThreads.mockResolvedValue({
      threads: [
        {
          gmail_thread_id: "thread-1",
          subject_normalized: "Series A deck review",
          participants_json: [],
          last_message_internal_at: "2026-03-12T10:00:00.000Z",
          has_unread: true,
          snippet: "Snippet fallback",
          ai_summary_preview: "AI summary preview text",
        },
      ],
      page: 1,
      limit: 10,
      has_more: false,
    });

    render(<StarterHome />);

    expect(await screen.findByText("AI summary preview text")).toBeInTheDocument();
    expect(screen.queryByText("Snippet fallback")).not.toBeInTheDocument();
  });

  it("falls back to snippet when AI summary is empty", async () => {
    mocks.fetchInboxThreads.mockResolvedValue({
      threads: [
        {
          gmail_thread_id: "thread-2",
          subject_normalized: "Budget update",
          participants_json: [],
          last_message_internal_at: "2026-03-12T12:00:00.000Z",
          has_unread: false,
          snippet: "Use snippet fallback preview",
          ai_summary_preview: "",
        },
      ],
      page: 1,
      limit: 10,
      has_more: false,
    });

    render(<StarterHome />);

    expect(await screen.findByText("Use snippet fallback preview")).toBeInTheDocument();
  });
});
