import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeMemories } from "@/test/test-utils";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  useMemories: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/lib/hooks/useMemories", () => ({
  useMemories: mocks.useMemories,
}));

import MemoriesPage, { groupMemoriesByDate } from "./page";

describe("MemoriesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useMemories.mockReturnValue({
      memories: makeMemories(),
      loading: false,
    });
  });

  it("groups daily memories by recency buckets", () => {
    const grouped = groupMemoriesByDate([
      { date: new Date().toISOString().slice(0, 10), source_file: "daily/today.md", access_count: 1 },
      { date: "2000-01-01", source_file: "daily/old.md", access_count: 1 },
    ]);
    expect(grouped[0]?.label).toBe("Today");
    expect(grouped.at(-1)?.label).toBe("Older");
  });

  it("navigates to long-term and daily memory routes", () => {
    render(<MemoriesPage />);

    fireEvent.click(screen.getByText("MEMORY.md"));
    fireEvent.click(screen.getByText("2026-03-06"));

    expect(mocks.push).toHaveBeenCalledWith("/chat/memories/long-term");
    expect(mocks.push).toHaveBeenCalledWith("/chat/memories/daily/2026-03-06");
  });
});
