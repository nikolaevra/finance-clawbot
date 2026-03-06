import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeToolCatalogEntry } from "@/test/test-utils";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  fetchSkill: vi.fn(),
  updateSkill: vi.fn(),
  deleteSkill: vi.fn(),
  fetchToolCatalog: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
  useParams: () => ({ name: "budget-skill" }),
}));

vi.mock("@/lib/api", () => ({
  fetchSkill: mocks.fetchSkill,
  updateSkill: mocks.updateSkill,
  deleteSkill: mocks.deleteSkill,
  fetchToolCatalog: mocks.fetchToolCatalog,
}));

import SkillEditorPage, { getActiveMentionAtCursor } from "./page";

describe("Skill editor page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchSkill.mockResolvedValue({ name: "budget-skill", content: "Use @memory_re" });
    mocks.fetchToolCatalog.mockResolvedValue([
      makeToolCatalogEntry({ name: "memory_read" }),
      makeToolCatalogEntry({ name: "memory_search" }),
    ]);
    mocks.updateSkill.mockResolvedValue(undefined);
    mocks.deleteSkill.mockResolvedValue(undefined);
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  it("detects active mentions around cursor positions", () => {
    expect(getActiveMentionAtCursor("call @memory_re", 15)).toEqual({
      start: 5,
      end: 15,
      query: "memory_re",
    });
    expect(getActiveMentionAtCursor("email@domain.com", 12)).toBeNull();
  });

  it("inserts selected tool mention and saves content", async () => {
    render(<SkillEditorPage />);

    const textarea = (await screen.findByPlaceholderText(/name: my-skill/i)) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Run @memory_" } });
    fireEvent.click((await screen.findAllByText("memory_read"))[0]);

    await waitFor(() =>
      expect(textarea.value).toContain("@memory_read")
    );

    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(mocks.updateSkill).toHaveBeenCalledWith(
        "budget-skill",
        expect.stringContaining("@memory_read")
      )
    );
  });
});
