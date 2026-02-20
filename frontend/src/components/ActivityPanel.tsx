"use client";

import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import { useActivity } from "./ActivityProvider";
import {
  Activity,
  ArrowRightLeft,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Trash2,
  Wrench,
  Play,
  Pause,
  SkipForward,
  Zap,
  Server,
  PanelRightClose,
  Check,
  X,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { ActivityEvent, ApprovalPreviewItem } from "@/types";
import { approveWorkflowRun, cancelWorkflowRun } from "@/lib/api";

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

const EVENT_CONFIG: Record<
  string,
  { icon: typeof Activity; color: string; pulse?: boolean }
> = {
  tool_dispatch: { icon: ArrowRightLeft, color: "text-blue-400", pulse: true },
  tool_complete: { icon: CheckCircle2, color: "text-emerald-400" },
  tool_error: { icon: XCircle, color: "text-red-400" },
  workflow_start: { icon: Play, color: "text-violet-400", pulse: true },
  step_start: { icon: Loader2, color: "text-sky-400", pulse: true },
  step_complete: { icon: CheckCircle2, color: "text-emerald-400" },
  step_failed: { icon: XCircle, color: "text-red-400" },
  step_skipped: { icon: SkipForward, color: "text-zinc-400" },
  approval_gate: { icon: Pause, color: "text-amber-400" },
  workflow_complete: { icon: Zap, color: "text-emerald-400" },
  workflow_failed: { icon: AlertTriangle, color: "text-red-400" },
  workflow_done: { icon: CheckCircle2, color: "text-emerald-500" },
};

function ActorBadge({ actor }: { actor: "gateway" | "lobster" }) {
  if (actor === "gateway") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-blue-400 leading-none">
        <Server size={9} />
        Gateway
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-orange-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-orange-400 leading-none">
      <Wrench size={9} />
      Lobster
    </span>
  );
}

function PreviewBlock({ items }: { items: ApprovalPreviewItem[] }) {
  if (!items || items.length === 0) return null;

  return (
    <div className="mt-1.5 space-y-1.5">
      {items.map((item, idx) => (
        <div
          key={idx}
          className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200/60 dark:border-amber-800/40 p-2"
        >
          {item.summary && (
            <p className="text-[11px] font-medium text-amber-700 dark:text-amber-300 mb-1">
              {item.summary}
            </p>
          )}
          {item.type === "suggestions" && item.sample && (
            <div className="space-y-0.5">
              {item.sample.map((s, si) => (
                <div
                  key={si}
                  className="flex items-center gap-1.5 text-[10px] text-zinc-600 dark:text-zinc-400"
                >
                  <span className="shrink-0 text-amber-500">&bull;</span>
                  <span className="truncate">
                    {String(s.suggested_category || s.category || "")}
                    {s.reason ? ` — ${String(s.reason).slice(0, 60)}` : ""}
                  </span>
                </div>
              ))}
              {(item.count || 0) > (item.sample?.length || 0) && (
                <p className="text-[10px] text-zinc-400 italic">
                  +{(item.count || 0) - (item.sample?.length || 0)} more...
                </p>
              )}
            </div>
          )}
          {item.type === "anomalies" && item.sample && (
            <div className="space-y-0.5">
              {item.sample.map((a, ai) => (
                <div
                  key={ai}
                  className="flex items-center gap-1.5 text-[10px] text-zinc-600 dark:text-zinc-400"
                >
                  <span className="shrink-0 text-red-400">&bull;</span>
                  <span className="truncate">
                    {String(a.memo || a.contact || "")} — $
                    {String(a.amount || "")}
                  </span>
                </div>
              ))}
              {(item.count || 0) > (item.sample?.length || 0) && (
                <p className="text-[10px] text-zinc-400 italic">
                  +{(item.count || 0) - (item.sample?.length || 0)} more...
                </p>
              )}
            </div>
          )}
          {item.type === "report" && item.preview && (
            <p className="text-[10px] text-zinc-600 dark:text-zinc-400 line-clamp-4 whitespace-pre-wrap">
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
    color: "text-zinc-400",
  };
  const Icon = config.icon;
  const isError =
    event.type.includes("error") || event.type.includes("failed");
  const isDone = event.type === "workflow_done" || event.type === "workflow_complete";

  return (
    <div className="group flex gap-2.5 py-2 px-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors">
      <div className="flex flex-col items-center pt-0.5">
        <div
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
            config.pulse ? "bg-current/10 ring-2 ring-current/20" : ""
          } ${config.color}`}
        >
          <Icon size={12} className={config.pulse ? "animate-pulse" : ""} />
        </div>
        <div className="mt-1 w-px flex-1 bg-zinc-200 dark:bg-zinc-700/60" />
      </div>

      <div className="flex-1 min-w-0 pb-1">
        <div className="flex items-center gap-1.5 mb-0.5">
          <ActorBadge actor={event.actor} />
          <span className="text-[10px] text-zinc-400 dark:text-zinc-500 tabular-nums">
            {formatTime(event.timestamp)}
          </span>
        </div>
        <p
          className={`text-xs leading-relaxed ${
            isError
              ? "text-red-500 dark:text-red-400"
              : isDone
                ? "text-emerald-600 dark:text-emerald-400 font-medium"
                : "text-zinc-700 dark:text-zinc-300"
          }`}
        >
          {event.message}
        </p>
        {event.detail && (
          <p className="mt-0.5 text-[11px] text-zinc-400 dark:text-zinc-500 leading-relaxed">
            {event.detail}
          </p>
        )}
        {event.preview?.items && event.preview.items.length > 0 && (
          <PreviewBlock items={event.preview.items} />
        )}
      </div>
    </div>
  );
}

// --- Workflow run tracking from events ---

interface TrackedRun {
  runId: string;
  name: string;
  status: "running" | "paused" | "completed" | "failed";
  steps: { id: string; status: string }[];
  approvalPrompt?: string;
  approvalPreview?: { items: ApprovalPreviewItem[] };
  completionMessage?: string;
}

function useTrackedRuns(events: ActivityEvent[]): TrackedRun[] {
  return useMemo(() => {
    const runs = new Map<string, TrackedRun>();

    for (const e of events) {
      if (!e.run_id) continue;
      const existing = runs.get(e.run_id);

      switch (e.type) {
        case "workflow_start":
          runs.set(e.run_id, {
            runId: e.run_id,
            name: e.workflow_name || "Workflow",
            status: "running",
            steps: [],
          });
          break;
        case "step_start":
          if (existing) {
            const stepIdx = existing.steps.findIndex(
              (s) => s.id === e.step_id
            );
            if (stepIdx >= 0) {
              existing.steps[stepIdx].status = "running";
            } else {
              existing.steps.push({
                id: e.step_id || "?",
                status: "running",
              });
            }
          }
          break;
        case "step_complete":
          if (existing) {
            const stepIdx = existing.steps.findIndex(
              (s) => s.id === e.step_id
            );
            if (stepIdx >= 0) existing.steps[stepIdx].status = "completed";
          }
          break;
        case "step_failed":
          if (existing) {
            const stepIdx = existing.steps.findIndex(
              (s) => s.id === e.step_id
            );
            if (stepIdx >= 0) existing.steps[stepIdx].status = "failed";
            existing.status = "failed";
          }
          break;
        case "step_skipped":
          if (existing) {
            const stepIdx = existing.steps.findIndex(
              (s) => s.id === e.step_id
            );
            if (stepIdx >= 0) existing.steps[stepIdx].status = "skipped";
            else
              existing.steps.push({
                id: e.step_id || "?",
                status: "skipped",
              });
          }
          break;
        case "approval_gate":
          if (existing) {
            existing.status = "paused";
            existing.approvalPrompt = e.detail;
            if (e.preview) existing.approvalPreview = e.preview;
          }
          break;
        case "workflow_complete":
          if (existing) {
            existing.status = "completed";
            existing.completionMessage = e.message;
          }
          break;
        case "workflow_failed":
          if (existing) {
            existing.status = "failed";
            existing.completionMessage = e.message;
          }
          break;
      }
    }

    return Array.from(runs.values());
  }, [events]);
}

const STEP_DOT_COLORS: Record<string, string> = {
  running: "bg-blue-500 animate-pulse",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
  skipped: "bg-zinc-400",
  pending: "bg-zinc-300 dark:bg-zinc-600",
};

function RunCard({ run }: { run: TrackedRun }) {
  const [expanded, setExpanded] = useState(run.status === "paused");
  const [acting, setActing] = useState(false);

  const handleApprove = useCallback(
    async (approve: boolean) => {
      setActing(true);
      try {
        await approveWorkflowRun(run.runId, approve);
      } catch {
        /* swallow */
      } finally {
        setActing(false);
      }
    },
    [run.runId]
  );

  const handleCancel = useCallback(async () => {
    setActing(true);
    try {
      await cancelWorkflowRun(run.runId);
    } catch {
      /* swallow */
    } finally {
      setActing(false);
    }
  }, [run.runId]);

  const isTerminal = run.status === "completed" || run.status === "failed";

  return (
    <div
      className={`rounded-lg border overflow-hidden ${
        run.status === "paused"
          ? "border-amber-300 dark:border-amber-700/60 bg-amber-50/50 dark:bg-amber-900/10"
          : isTerminal
            ? "border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-800/30 opacity-70"
            : "border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/40"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        {expanded ? (
          <ChevronDown size={12} className="text-zinc-400 shrink-0" />
        ) : (
          <ChevronRight size={12} className="text-zinc-400 shrink-0" />
        )}
        {run.status === "paused" ? (
          <Pause size={12} className="text-amber-400 shrink-0" />
        ) : run.status === "completed" ? (
          <CheckCircle2 size={12} className="text-emerald-400 shrink-0" />
        ) : run.status === "failed" ? (
          <XCircle size={12} className="text-red-400 shrink-0" />
        ) : (
          <Loader2
            size={12}
            className="animate-spin text-blue-400 shrink-0"
          />
        )}
        <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300 truncate flex-1">
          {run.name}
        </span>
        <span
          className={`text-[10px] font-medium shrink-0 ${
            run.status === "paused"
              ? "text-amber-500"
              : run.status === "completed"
                ? "text-emerald-500"
                : run.status === "failed"
                  ? "text-red-500"
                  : "text-blue-400"
          }`}
        >
          {run.status === "paused"
            ? "Needs approval"
            : run.status === "completed"
              ? "Completed"
              : run.status === "failed"
                ? "Failed"
                : "Running"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/40 px-3 py-2 space-y-2">
          {/* Step dots */}
          <div className="flex items-center gap-1">
            {run.steps.map((step) => (
              <div
                key={step.id}
                className={`h-2 flex-1 rounded-full ${STEP_DOT_COLORS[step.status] || STEP_DOT_COLORS.pending}`}
                title={`${step.id}: ${step.status}`}
              />
            ))}
          </div>

          {/* Approval prompt + preview + actions */}
          {run.status === "paused" && (
            <div className="space-y-2">
              {run.approvalPrompt && (
                <p className="text-[11px] text-amber-700 dark:text-amber-300 leading-relaxed">
                  {run.approvalPrompt}
                </p>
              )}
              {run.approvalPreview?.items && run.approvalPreview.items.length > 0 && (
                <PreviewBlock items={run.approvalPreview.items} />
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleApprove(true)}
                  disabled={acting}
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  {acting ? (
                    <Loader2 size={10} className="animate-spin" />
                  ) : (
                    <Check size={10} />
                  )}
                  Approve
                </button>
                <button
                  onClick={() => handleApprove(false)}
                  disabled={acting}
                  className="inline-flex items-center gap-1 rounded-md bg-zinc-200 dark:bg-zinc-700 px-2.5 py-1 text-[11px] font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-zinc-600 disabled:opacity-50 transition-colors"
                >
                  <X size={10} />
                  Reject
                </button>
              </div>
            </div>
          )}

          {/* Completion summary */}
          {isTerminal && run.completionMessage && (
            <p className={`text-[11px] leading-relaxed ${
              run.status === "completed"
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            }`}>
              {run.completionMessage}
            </p>
          )}

          {/* Cancel for running */}
          {run.status === "running" && (
            <button
              onClick={handleCancel}
              disabled={acting}
              className="inline-flex items-center gap-1 rounded-md bg-zinc-200 dark:bg-zinc-700 px-2.5 py-1 text-[11px] font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-zinc-600 disabled:opacity-50 transition-colors"
            >
              <X size={10} />
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function WorkflowRunsSection({ events }: { events: ActivityEvent[] }) {
  const runs = useTrackedRuns(events);
  if (runs.length === 0) return null;

  const active = runs.filter(
    (r) => r.status === "running" || r.status === "paused"
  );
  const terminal = runs.filter(
    (r) => r.status === "completed" || r.status === "failed"
  );

  return (
    <div className="px-3 py-2 space-y-2 border-b border-zinc-200 dark:border-zinc-800 shrink-0">
      {active.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
            Active runs
          </p>
          {active.map((run) => (
            <RunCard key={run.runId} run={run} />
          ))}
        </div>
      )}
      {terminal.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
            Recent
          </p>
          {terminal.map((run) => (
            <RunCard key={run.runId} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Floating toggle button shown on the right edge when the panel is collapsed. */
export function ActivityToggleButton() {
  const { togglePanel, isPanelOpen, events } = useActivity();

  const hasRecentActivity =
    events.length > 0 &&
    Date.now() - new Date(events[events.length - 1].timestamp).getTime() <
      30_000;

  if (isPanelOpen) return null;

  return (
    <button
      onClick={togglePanel}
      className="fixed right-0 top-1/2 -translate-y-1/2 z-40 hidden md:flex items-center gap-1.5 rounded-l-lg bg-zinc-800 dark:bg-zinc-700 px-2 py-3 text-zinc-300 hover:bg-zinc-700 dark:hover:bg-zinc-600 transition-colors shadow-lg border border-r-0 border-zinc-700 dark:border-zinc-600"
      title="System Activity"
    >
      <Activity size={16} />
      {hasRecentActivity && (
        <span className="absolute -top-1 -left-1 h-2.5 w-2.5 rounded-full bg-blue-500 animate-pulse" />
      )}
    </button>
  );
}

/** The activity panel content rendered inside a ResizablePanel. */
export default function ActivityPanel() {
  const { events, isConnected, togglePanel, clearEvents } = useActivity();
  const scrollRef = useRef<HTMLDivElement>(null);
  const isNearBottom = useRef(true);

  useEffect(() => {
    if (isNearBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    isNearBottom.current = scrollHeight - scrollTop - clientHeight < 60;
  };

  return (
    <div className="flex h-full flex-col bg-white dark:bg-zinc-950 overflow-hidden">
      {/* Header */}
      <div className="border-b border-zinc-200 dark:border-zinc-800 px-4 py-3 shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
            System Activity
          </h2>
          <span
            className={`h-2 w-2 rounded-full ${
              isConnected ? "bg-emerald-500" : "bg-red-500"
            }`}
            title={isConnected ? "Connected" : "Disconnected"}
          />
          <span className="text-[10px] text-zinc-400">
            {isConnected ? "Live" : "Reconnecting..."}
          </span>
          <div className="flex-1" />
          {events.length > 0 && (
            <button
              onClick={clearEvents}
              className="flex items-center gap-1 text-[10px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
            >
              <Trash2 size={10} />
              Clear
            </button>
          )}
          <button
            onClick={togglePanel}
            className="flex items-center justify-center h-6 w-6 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            title="Close panel"
          >
            <PanelRightClose size={14} />
          </button>
        </div>
        <p className="text-[11px] text-zinc-500 mt-0.5">
          Gateway &amp; Lobster orchestration events
        </p>
      </div>

      {/* Workflow runs with step progress + approval actions */}
      <WorkflowRunsSection events={events} />

      {/* Event timeline */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <Activity
              size={32}
              className="mb-3 text-zinc-300 dark:text-zinc-600"
            />
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No activity yet
            </p>
            <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
              Events from Gateway tool calls and Lobster workflow execution will
              appear here in real time
            </p>
          </div>
        ) : (
          <div className="py-1">
            {events.map((event, i) => (
              <EventRow key={`${event.timestamp}-${i}`} event={event} />
            ))}
          </div>
        )}
      </div>

      {/* Footer with stats */}
      {events.length > 0 && (
        <div className="border-t border-zinc-200 dark:border-zinc-800 px-4 py-2 flex items-center justify-between text-[10px] text-zinc-400">
          <span>{events.length} events</span>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
              Gateway: {events.filter((e) => e.actor === "gateway").length}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-orange-400" />
              Lobster: {events.filter((e) => e.actor === "lobster").length}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
