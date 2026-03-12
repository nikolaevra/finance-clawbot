"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  Activity,
  ArrowRightLeft,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Trash2,
  Wrench,
  PanelRightClose,
} from "lucide-react";
import type { ActivityEvent, ApprovalPreviewItem } from "@/types";
import { useActivity } from "./ActivityProvider";

const HIDDEN_ACTIVITY_TYPES = new Set([
  "agent_streaming",
  "streaming_response",
  "gateway_task",
  "lobster_task",
]);

const HIDDEN_SOURCE_KEYWORDS = ["gateway_task", "lobster_task"];

function shouldHideEvent(event: ActivityEvent): boolean {
  if (HIDDEN_ACTIVITY_TYPES.has(event.type)) return true;
  const source = (event.source || "").toLowerCase();
  return HIDDEN_SOURCE_KEYWORDS.some((needle) => source.includes(needle));
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatVerboseValue(value: unknown): string {
  if (value == null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const EVENT_CONFIG: Record<
  string,
  { icon: typeof Activity; color: string; pulse?: boolean }
> = {
  tool_dispatch: { icon: ArrowRightLeft, color: "text-blue-400", pulse: true },
  tool_complete: { icon: CheckCircle2, color: "text-emerald-400" },
  tool_error: { icon: XCircle, color: "text-red-400" },
  workflow_start: { icon: Loader2, color: "text-blue-400", pulse: true },
  step_start: { icon: Loader2, color: "text-blue-400", pulse: true },
  step_complete: { icon: CheckCircle2, color: "text-emerald-400" },
  step_failed: { icon: XCircle, color: "text-red-400" },
  step_skipped: { icon: Loader2, color: "text-foreground/30" },
  approval_gate: { icon: AlertTriangle, color: "text-amber-400" },
  workflow_complete: { icon: CheckCircle2, color: "text-emerald-400" },
  workflow_failed: { icon: AlertTriangle, color: "text-red-400" },
  workflow_done: { icon: CheckCircle2, color: "text-emerald-400" },
};

function ActorBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-blue-400/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-400/80 leading-none">
      <Wrench size={8} />
      Agent
    </span>
  );
}

function PreviewBlock({ items }: { items: ApprovalPreviewItem[] }) {
  if (!items || items.length === 0) return null;

  return (
    <div className="mt-2 space-y-1.5">
      {items.map((item, idx) => (
        <div
          key={idx}
          className="rounded-xl bg-amber-400/[0.06] ring-1 ring-amber-400/10 p-2.5"
        >
          {item.summary && (
            <p className="text-[11px] font-medium text-amber-400/80 mb-1">
              {item.summary}
            </p>
          )}
          {item.type === "report" && item.preview && (
            <p className="text-[10px] text-foreground/60 line-clamp-4 whitespace-pre-wrap">
              {item.preview}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function EventRow({ event }: { event: ActivityEvent }) {
  const config = EVENT_CONFIG[event.type] || {
    icon: Activity,
    color: "text-foreground/30",
  };
  const Icon = config.icon;
  const isError =
    event.type.includes("error") || event.type.includes("failed");

  return (
    <div className="group flex gap-2.5 py-2 px-3 hover:bg-foreground/[0.03] transition-colors">
      <div className="flex flex-col items-center pt-0.5">
        <div className={`flex h-5 w-5 shrink-0 items-center justify-center ${config.color}`}>
          <Icon size={12} strokeWidth={1.5} className={config.pulse ? "animate-pulse" : ""} />
        </div>
        <div className="mt-1 w-px flex-1 bg-foreground/[0.06]" />
      </div>

      <div className="flex-1 min-w-0 pb-1">
        <div className="flex items-center gap-1.5 mb-0.5">
          <ActorBadge />
          <span className="text-[10px] text-foreground/45 tabular-nums">
            {formatTime(event.timestamp)}
          </span>
        </div>
        <p
          className={`text-xs leading-relaxed ${
            isError ? "text-red-400/80" : "text-foreground/80"
          }`}
        >
          {event.message}
        </p>
        {event.detail && (
          <p className="mt-0.5 text-[11px] text-foreground/50 leading-relaxed">
            {event.detail}
          </p>
        )}
        {event.preview?.items && event.preview.items.length > 0 && (
          <PreviewBlock items={event.preview.items} />
        )}
        {event.verbose_data && Object.keys(event.verbose_data).length > 0 && (
          <details className="mt-1.5 rounded-lg bg-foreground/[0.03] p-2">
            <summary className="cursor-pointer text-[10px] text-foreground/60">
              Metadata
            </summary>
            <div className="mt-1.5 space-y-1">
              {Object.entries(event.verbose_data).map(([key, value]) => (
                <p
                  key={key}
                  className="text-[10px] text-foreground/55 leading-relaxed break-all"
                >
                  <span className="text-foreground/40">{key}:</span>{" "}
                  {formatVerboseValue(value)}
                </p>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

export function ActivityToggleButton() {
  const { togglePanel, isPanelOpen, events } = useActivity();
  const visibleEvents = events.filter((e) => !shouldHideEvent(e));
  const hasRecentActivity = visibleEvents.length > 0;

  if (isPanelOpen) return null;

  return (
    <button
      onClick={togglePanel}
      className="fixed right-0 top-1/2 -translate-y-1/2 z-40 hidden md:flex items-center gap-1.5 rounded-l-xl bg-foreground/[0.06] px-2 py-3.5 text-foreground/50 hover:text-foreground/70 hover:bg-foreground/[0.1] transition-all shadow-lg shadow-black/20 ring-1 ring-foreground/[0.08] ring-r-0"
      title="System Activity"
    >
      <Activity size={14} strokeWidth={1.5} />
      {hasRecentActivity && (
        <span className="absolute -top-1 -left-1 h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
      )}
    </button>
  );
}

export default function ActivityPanel() {
  const { events, isConnected, togglePanel, clearEvents } = useActivity();
  const visibleEvents = useMemo(
    () => events.filter((e) => !shouldHideEvent(e)),
    [events]
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const isNearBottom = useRef(true);

  useEffect(() => {
    if (isNearBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [visibleEvents]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    isNearBottom.current = scrollHeight - scrollTop - clientHeight < 60;
  };

  return (
    <div className="flex h-full flex-col bg-foreground/[0.02] overflow-hidden">
      <div className="px-4 py-4 shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-foreground">
            Activity
          </h2>
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              isConnected ? "bg-emerald-400" : "bg-red-400"
            }`}
            title={isConnected ? "Connected" : "Disconnected"}
          />
          <span className="text-[10px] text-foreground/50">
            {isConnected ? "Live" : "Reconnecting..."}
          </span>
          <div className="flex-1" />
          {visibleEvents.length > 0 && (
            <button
              onClick={clearEvents}
              className="flex items-center gap-1 text-[10px] text-foreground/40 hover:text-foreground/60"
            >
              <Trash2 size={10} strokeWidth={1.5} />
              Clear
            </button>
          )}
          <button
            onClick={togglePanel}
            className="flex items-center justify-center h-6 w-6 rounded-lg text-foreground/40 hover:text-foreground/60 hover:bg-foreground/[0.06]"
            title="Close panel"
          >
            <PanelRightClose size={13} strokeWidth={1.5} />
          </button>
        </div>
        <p className="text-[11px] text-foreground/45 mt-0.5">
          Verbose automation steps and event payloads
        </p>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {visibleEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <Activity
              size={28}
              className="mb-3 text-foreground/10"
              strokeWidth={1.5}
            />
            <p className="text-sm text-foreground/50">
              No activity yet
            </p>
            <p className="text-xs text-foreground/35 mt-1">
              Events will appear here in real time
            </p>
          </div>
        ) : (
          <div className="py-1">
            {visibleEvents.map((event, i) => (
              <EventRow key={`${event.timestamp}-${i}`} event={event} />
            ))}
          </div>
        )}
      </div>

      {visibleEvents.length > 0 && (
        <div className="border-t border-foreground/[0.06] px-4 py-2 flex items-center justify-between text-[10px] text-foreground/45">
          <span>{visibleEvents.length} events</span>
          <span className="inline-flex items-center gap-1">
            <span className="h-1 w-1 rounded-full bg-blue-400/60" />
            Agent events
          </span>
        </div>
      )}
    </div>
  );
}

