import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  sourceHref,
  sourceLabel,
  typeBadgeClasses,
  typeLabel,
} from "./SourcesCitation";
import SourcesCitation from "./SourcesCitation";

describe("SourcesCitation", () => {
  it("maps labels, hrefs, and badge types", () => {
    expect(sourceLabel("MEMORY.md")).toBe("Long-term Memory");
    expect(sourceHref("daily/2026-03-06.md")).toBe("/chat/memories/daily/2026-03-06.md");
    expect(typeLabel("documents/report.pdf")).toBe("PDF");
    expect(typeBadgeClasses("documents/report.pdf")).toContain("emerald");
  });

  it("shows a collapsed preview and expands remaining sources", () => {
    render(
      <SourcesCitation
        sources={[
          { source_file: "MEMORY.md", score: 1 },
          { source_file: "daily/2026-03-06.md", score: 0.9 },
          { source_file: "documents/report.pdf", score: 0.8 },
        ]}
      />
    );

    expect(screen.getByText("3 sources referenced")).toBeInTheDocument();
    expect(screen.getByText("+1 more")).toBeInTheDocument();
    expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("+1 more"));

    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });
});
