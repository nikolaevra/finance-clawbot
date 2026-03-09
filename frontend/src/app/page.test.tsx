import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
  getUser: vi.fn(),
  appShell: vi.fn(),
  starterHome: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

vi.mock("@/lib/supabase-server", () => ({
  createServerSupabase: async () => ({
    auth: {
      getUser: mocks.getUser,
    },
  }),
}));

vi.mock("@/components/AppShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => {
    mocks.appShell();
    return <div data-testid="app-shell">{children}</div>;
  },
}));

vi.mock("@/components/StarterHome", () => ({
  default: (props: { withinShell?: boolean }) => {
    mocks.starterHome(props);
    return <div data-testid="starter-home" />;
  },
}));

import Home from "./page";

describe("app home page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects unauthenticated users to login", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null } });
    await expect(Home()).rejects.toThrow("NEXT_REDIRECT");
    expect(mocks.redirect).toHaveBeenCalledWith("/login");
  });

  it("renders dedicated home inside app shell for authenticated users", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { id: "user-1" } } });
    const view = await Home();
    const { getByTestId } = render(view);
    expect(getByTestId("app-shell")).toBeInTheDocument();
    expect(getByTestId("starter-home")).toBeInTheDocument();
    expect(mocks.starterHome).toHaveBeenCalledWith(
      expect.objectContaining({ withinShell: true })
    );
  });
});
