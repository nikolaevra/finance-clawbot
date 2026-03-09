import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getUser: vi.fn(),
  redirectMock: vi.fn((url: URL) => ({ kind: "redirect", url })),
  nextMock: vi.fn(({ request }: { request: Request }) => ({
    kind: "next",
    request,
    cookies: { set: vi.fn() },
  })),
}));

vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({
    auth: {
      getUser: mocks.getUser,
    },
  }),
}));

vi.mock("next/server", () => ({
  NextResponse: {
    next: mocks.nextMock,
    redirect: mocks.redirectMock,
  },
}));

import { middleware } from "./middleware";

describe("middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function makeRequest(pathname: string) {
    const url = new URL(`http://localhost:3000${pathname}`);
    return {
      nextUrl: {
        pathname: url.pathname,
        clone: () => new URL(url.toString()),
      },
      cookies: {
        getAll: () => [],
        set: vi.fn(),
      },
    } as unknown as Parameters<typeof middleware>[0];
  }

  it("redirects unauthenticated chat requests to login", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null } });
    const res = await middleware(makeRequest("/chat"));
    expect(res.kind).toBe("redirect");
    expect(res.url.pathname).toBe("/login");
  });

  it("redirects authenticated login requests to home", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { id: "user-1" } } });
    const res = await middleware(makeRequest("/login"));
    expect(res.kind).toBe("redirect");
    expect(res.url.pathname).toBe("/");
  });
});
