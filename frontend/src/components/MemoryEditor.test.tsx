import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  fetchMemoryAccessLog: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/lib/api", () => ({
  fetchMemoryAccessLog: mocks.fetchMemoryAccessLog,
}));

import MemoryEditor from "./MemoryEditor";

describe("MemoryEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchMemoryAccessLog.mockResolvedValue([
      {
        id: "log-1",
        conversation_id: "conv-1",
        conversation_title: "Budget chat",
        tool_name: "memory_read",
        created_at: "2026-03-06T12:00:00.000Z",
      },
      {
        id: "log-2",
        conversation_id: "conv-1",
        conversation_title: "Budget chat",
        tool_name: "memory_search",
        created_at: "2026-03-06T12:01:00.000Z",
      },
    ]);
  });

  it("loads access log, saves changes, and links back to conversations", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryEditor
        sourceFile="daily/2026-03-06.md"
        title="Daily"
        initialContent="start"
        onSave={onSave}
      />
    );

    expect(await screen.findByText(/Referenced 2 times/i)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Memory content..."), {
      target: { value: "updated" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith("updated"));

    fireEvent.click(screen.getByText("Budget chat"));
    expect(mocks.push).toHaveBeenCalledWith("/chat/conv-1");
  });
});
