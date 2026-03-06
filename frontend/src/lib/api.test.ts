import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  loggerWarn: vi.fn(),
}));

vi.mock("./supabase", () => ({
  createClient: () => ({
    auth: {
      getSession: mocks.getSession,
    },
  }),
}));

vi.mock("./logger", () => ({
  logger: {
    warn: mocks.loggerWarn,
  },
}));

import {
  fetchConversations,
  fetchMemoryAccessLog,
  getActivityStreamUrl,
  uploadDocument,
} from "./api";

describe("api", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "token-123" } },
    });
    vi.stubGlobal("fetch", vi.fn());
  });

  it("builds the activity stream url safely", () => {
    expect(getActivityStreamUrl("a b/c?d")).toBe(
      "http://localhost:5001/api/activity/events?token=a%20b%2Fc%3Fd"
    );
  });

  it("preserves path segments when fetching memory access logs", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );

    await fetchMemoryAccessLog("daily/2026-03-06.md");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:5001/api/memories/access-log/daily/2026-03-06.md",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer token-123",
        }),
      })
    );
  });

  it("throws when auth is missing", async () => {
    mocks.getSession.mockResolvedValue({ data: { session: null } });

    await expect(fetchConversations()).rejects.toThrow("Not authenticated");
  });

  it("surfaces upload API errors from the response body", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "Nope" }), { status: 400 })
    );

    await expect(
      uploadDocument(new File(["hello"], "invoice.pdf", { type: "application/pdf" }))
    ).rejects.toThrow("Failed to upload document");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:5001/api/documents/upload",
      expect.objectContaining({
        method: "POST",
        headers: { Authorization: "Bearer token-123" },
      })
    );
    expect(mocks.loggerWarn).toHaveBeenCalledWith(
      "api_request_failed",
      expect.objectContaining({
        endpoint: "/api/documents/upload",
        method: "POST",
        status: 400,
        errorBody: "Nope",
      })
    );
  });
});
