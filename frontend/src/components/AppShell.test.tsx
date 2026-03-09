import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  pathname: "/",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
}));

vi.mock("@/components/NavBar", () => ({
  default: () => <div data-testid="navbar" />,
}));

vi.mock("@/components/ActivityProvider", () => {
  return {
    __esModule: true,
    default: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="activity-provider">{children}</div>
    ),
    useActivityInternal: () => ({
      panelRef: null,
      isPanelOpen: false,
      onPanelResize: vi.fn(),
    }),
  };
});

vi.mock("@/components/ActivityPanel", () => ({
  __esModule: true,
  default: () => <div data-testid="activity-panel" />,
  ActivityToggleButton: () => <div data-testid="activity-toggle" />,
}));

vi.mock("@/components/ConversationProvider", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="conversation-provider">{children}</div>
  ),
}));

vi.mock("@/components/ChatSidebar", () => ({
  __esModule: true,
  default: () => <div data-testid="chat-sidebar" />,
  ChatSidebarToggle: () => <div data-testid="chat-sidebar-toggle" />,
  MobileChatSidebar: () => <div data-testid="mobile-chat-sidebar" />,
  MobileChatSidebarToggle: () => <div data-testid="mobile-chat-sidebar-toggle" />,
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div data-testid="resizable-handle" />,
}));

import AppShell from "./AppShell";

describe("AppShell", () => {
  it("hides chat secondary sidebar on root home", () => {
    mocks.pathname = "/";
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );
    expect(screen.queryByTestId("chat-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-sidebar-toggle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mobile-chat-sidebar")).not.toBeInTheDocument();
  });

  it("shows chat secondary sidebar on chat routes", () => {
    mocks.pathname = "/chat/conv-1";
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );
    expect(screen.getByTestId("chat-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("chat-sidebar-toggle")).toBeInTheDocument();
  });
});
