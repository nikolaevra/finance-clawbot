import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeDocument } from "@/test/test-utils";

const mocks = vi.hoisted(() => ({
  fetchDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  fetchDocuments: mocks.fetchDocuments,
  uploadDocument: mocks.uploadDocument,
  deleteDocument: mocks.deleteDocument,
}));

import DocumentsPage, { formatFileSize } from "./page";

describe("DocumentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("confirm", vi.fn(() => true));
    mocks.fetchDocuments.mockResolvedValue([]);
    mocks.uploadDocument.mockResolvedValue(makeDocument({ id: "doc-2" }));
    mocks.deleteDocument.mockResolvedValue(undefined);
  });

  it("formats file sizes for display", () => {
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(2048)).toBe("2.0 KB");
    expect(formatFileSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });

  it("rejects unsupported uploads and can delete an existing document", async () => {
    mocks.fetchDocuments.mockResolvedValue([makeDocument()]);
    render(<DocumentsPage />);

    fireEvent.drop(screen.getByText(/Click or drag files to upload/i).closest("div") as HTMLElement, {
      dataTransfer: {
        files: [new File(["bad"], "notes.txt", { type: "text/plain" })],
      },
    });

    await waitFor(() => expect(mocks.uploadDocument).not.toHaveBeenCalled());
    expect(mocks.uploadDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTitle("Delete document"));
    await waitFor(() => expect(mocks.deleteDocument).toHaveBeenCalledWith("doc-1"));
  });

  it("polls until processing documents finish", async () => {
    vi.spyOn(globalThis, "setInterval").mockImplementation(((fn: TimerHandler) => {
      if (typeof fn === "function") fn();
      return 1 as unknown as ReturnType<typeof setInterval>;
    }) as typeof setInterval);

    mocks.fetchDocuments
      .mockResolvedValueOnce([makeDocument({ status: "processing" })])
      .mockResolvedValueOnce([makeDocument({ status: "ready" })]);

    render(<DocumentsPage />);

    expect(await screen.findByText("Processing")).toBeInTheDocument();

    await waitFor(() =>
      expect(mocks.fetchDocuments).toHaveBeenCalledTimes(2)
    );
  });
});
