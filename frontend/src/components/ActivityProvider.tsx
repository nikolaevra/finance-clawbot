"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import type { ActivityEvent } from "@/types";
import { getActivityStreamUrl, getAuthToken } from "@/lib/api";

const MAX_EVENTS = 200;
const RECONNECT_DELAY = 3000;

interface ActivityContextValue {
  events: ActivityEvent[];
  isConnected: boolean;
  hasActivity: boolean;
  isPanelOpen: boolean;
  togglePanel: () => void;
  clearEvents: () => void;
  panelRef: React.RefObject<PanelImperativeHandle | null>;
}

const ActivityContext = createContext<ActivityContextValue>({
  events: [],
  isConnected: false,
  hasActivity: false,
  isPanelOpen: false,
  togglePanel: () => {},
  clearEvents: () => {},
  panelRef: { current: null },
});

export function useActivity() {
  return useContext(ActivityContext);
}

const TERMINAL_TYPES = new Set([
  "tool_complete",
  "tool_error",
  "step_complete",
  "step_failed",
  "step_skipped",
  "workflow_complete",
  "workflow_failed",
]);

export default function ActivityProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const panelRef = useRef<PanelImperativeHandle | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function connect() {
      if (cancelled) return;

      try {
        const token = await getAuthToken();
        if (cancelled) return;

        const url = getActivityStreamUrl(token);
        const es = new EventSource(url);
        eventSourceRef.current = es;

        es.addEventListener("activity", (e) => {
          if (cancelled) return;
          try {
            const data = JSON.parse(e.data) as {
              events: ActivityEvent[];
              cursor: number;
            };
            if (data.events?.length > 0) {
              setEvents((prev) => {
                const next = [...prev, ...data.events];
                return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
              });
            }
          } catch {
            /* ignore malformed frames */
          }
        });

        es.onopen = () => {
          if (!cancelled) setIsConnected(true);
        };

        es.onerror = () => {
          if (cancelled) return;
          setIsConnected(false);
          es.close();
          eventSourceRef.current = null;
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
        };
      } catch {
        if (!cancelled) {
          setIsConnected(false);
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
        }
      }
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, []);

  const hasActivity = events.some((e) => !TERMINAL_TYPES.has(e.type));

  const togglePanel = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) {
      panel.resize("30%");
      setIsPanelOpen(true);
    } else {
      panel.collapse();
      setIsPanelOpen(false);
    }
  }, []);

  const onPanelResize = useCallback(
    (size: { asPercentage: number; inPixels: number }) => {
      setIsPanelOpen(size.asPercentage > 0);
    },
    []
  );

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  const contextValue: ActivityContextValue & {
    onPanelResize: (size: { asPercentage: number; inPixels: number }) => void;
  } = {
    events,
    isConnected,
    hasActivity,
    isPanelOpen,
    togglePanel,
    clearEvents,
    panelRef,
    onPanelResize,
  };

  return (
    <ActivityContext.Provider value={contextValue}>
      {children}
    </ActivityContext.Provider>
  );
}

/** Extended hook that also returns the panel resize handler (used by layout). */
export function useActivityInternal() {
  const ctx = useContext(ActivityContext);
  return ctx as ActivityContextValue & {
    onPanelResize: (size: { asPercentage: number; inPixels: number }) => void;
  };
}
