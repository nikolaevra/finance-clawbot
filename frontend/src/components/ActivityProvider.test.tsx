import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect } from "react";

import type { ActivityEvent } from "@/types";

const mocks = vi.hoisted(() => ({
  getAuthToken: vi.fn(),
  getActivityStreamUrl: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getAuthToken: mocks.getAuthToken,
  getActivityStreamUrl: mocks.getActivityStreamUrl,
}));

import ActivityProvider, {
  useActivity,
  useActivityInternal,
} from "./ActivityProvider";

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Set<(event: MessageEvent) => void>>();
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)?.add(listener);
  }

  emit(type: string, payload: unknown) {
    const event = { data: JSON.stringify(payload) } as MessageEvent;
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}

function ActivityConsumer() {
  const activity = useActivity();
  const activityInternal = useActivityInternal();

  useEffect(() => {
    activityInternal.panelRef.current = {
      isCollapsed: () => !activity.isPanelOpen,
      resize: vi.fn(),
      collapse: vi.fn(),
    } as never;
  }, [activity.isPanelOpen, activityInternal.panelRef]);

  return (
    <>
      <div data-testid="count">{activity.events.length}</div>
      <div data-testid="connected">{String(activity.isConnected)}</div>
      <div data-testid="has-activity">{String(activity.hasActivity)}</div>
      <div data-testid="panel-open">{String(activity.isPanelOpen)}</div>
      <button onClick={activity.togglePanel}>toggle</button>
      <button onClick={activity.clearEvents}>clear</button>
    </>
  );
}

describe("ActivityProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    mocks.getAuthToken.mockResolvedValue("token-123");
    mocks.getActivityStreamUrl.mockReturnValue("http://example.test/events");
  });

  it("connects, appends activity events, trims to max size, and can clear them", async () => {
    render(
      <ActivityProvider>
        <ActivityConsumer />
      </ActivityProvider>
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0].onopen?.();
    });

    expect(screen.getByTestId("connected")).toHaveTextContent("true");

    const events: ActivityEvent[] = Array.from({ length: 205 }, (_, index) => ({
      type: "message_received",
      actor: "gateway",
      timestamp: `2026-03-06T12:${String(index).padStart(2, "0")}:00.000Z`,
      message: `event-${index}`,
    }));

    act(() => {
      MockEventSource.instances[0].emit("activity", {
        events,
        cursor: 205,
      });
    });

    expect(screen.getByTestId("count")).toHaveTextContent("200");
    expect(screen.getByTestId("has-activity")).toHaveTextContent("true");

    await act(async () => {
      screen.getByText("toggle").click();
    });
    expect(screen.getByTestId("panel-open")).toHaveTextContent("true");

    await act(async () => {
      screen.getByText("toggle").click();
    });
    expect(screen.getByTestId("panel-open")).toHaveTextContent("false");

    await act(async () => {
      screen.getByText("clear").click();
    });
    expect(screen.getByTestId("count")).toHaveTextContent("0");
  });

  it("ignores terminal-only activity and reconnects after stream errors", async () => {
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");

    render(
      <ActivityProvider>
        <ActivityConsumer />
      </ActivityProvider>
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0].emit("activity", {
        events: [
          {
            type: "tool_complete",
            actor: "gateway",
            timestamp: "2026-03-06T12:00:00.000Z",
            message: "done",
          },
        ],
        cursor: 1,
      });
      MockEventSource.instances[0].onerror?.();
    });

    expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 3000);
    expect(screen.getByTestId("has-activity")).toHaveTextContent("false");
  });
});
