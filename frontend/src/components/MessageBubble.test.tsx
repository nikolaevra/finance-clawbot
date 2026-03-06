import { describe, expect, it } from "vitest";

import {
  getToolSourceFiles,
  humanizeToolName,
  oneLine,
  toolActionLabel,
  toolResultPreview,
} from "./MessageBubble";

describe("MessageBubble helpers", () => {
  it("collects source files for memory and document tools", () => {
    expect(
      getToolSourceFiles(
        { name: "document_read", args: { filename: "invoice.pdf" } },
        ""
      )
    ).toEqual(["documents/invoice.pdf"]);

    expect(
      getToolSourceFiles(
        { name: "memory_search", args: {} },
        JSON.stringify({
          results: [
            { source_file: "daily/2026-03-05.md" },
            { source_file: "daily/2026-03-05.md" },
            { source_file: "documents/report.pdf" },
          ],
        })
      )
    ).toEqual(["daily/2026-03-05.md", "documents/report.pdf"]);
  });

  it("humanizes tool names and labels document actions", () => {
    expect(humanizeToolName("accounting_create_bill")).toBe(
      "accounting create bill"
    );
    expect(toolActionLabel("document_list")).toBe("Listed documents");
    expect(toolActionLabel("unknown_tool")).toBe("Tool result");
  });

  it("produces compact one-line previews", () => {
    expect(oneLine("  multi\nline   text  ")).toBe("multi line text");
    expect(
      toolResultPreview(
        { name: "memory_search", args: {} },
        JSON.stringify({ total: 3, message: "found matches" })
      )
    ).toBe("memory search: found matches");

    expect(
      toolResultPreview(
        { name: "gmail_reply_message", args: {} },
        JSON.stringify({ error: "Mailbox unavailable right now" })
      )
    ).toContain("error -");
  });
});
