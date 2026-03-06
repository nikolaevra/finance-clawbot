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
import { logger } from "@/lib/logger";

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
  workflow_start: { icon: Play, color: "text-blue-400", pulse: true },
  step_start: { icon: Loader2, color: "text-blue-400", pulse: true },
  step_complete: { icon: CheckCircle2, color: "text-emerald-400" },
  step_failed: { icon: XCircle, color: "text-red-400" },
  step_skipped: { icon: SkipForward, color: "text-foreground/30" },
  approval_gate: { icon: Pause, color: "text-amber-400" },
  workflow_complete: { icon: Zap, color: "text-emerald-400" },
  workflow_failed: { icon: AlertTriangle, color: "text-red-400" },
  workflow_done: { icon: CheckCircle2, color: "text-emerald-400" },
};

function ActorBadge({ actor }: { actor: "gateway" | "lobster" }) {
  if (actor === "gateway") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-400/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-400/80 leading-none">
        <Server size={8} />
        Gateway
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-foreground/[0.06] px-1.5 py-0.5 text-[10px] font-medium text-foreground/60 leading-none">
      <Wrench size={8} />
      Lobster
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
          {item.type === "suggestions" && item.sample && (
            <div className="space-y-0.5">
              {item.sample.map((s, si) => (
                <div
                  key={si}
                  className="flex items-center gap-1.5 text-[10px] text-foreground/60"
                >
                  <span className="shrink-0 text-amber-400/70">-</span>
                  <span className="truncate">
                    {String(s.suggested_category || s.category || "")}
                    {s.reason ? ` -- ${String(s.reason).slice(0, 60)}` : ""}
                  </span>
                </div>
              ))}
              {(item.count || 0) > (item.sample?.length || 0) && (
                <p className="text-[10px] text-foreground/40 italic">
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
                  className="flex items-center gap-1.5 text-[10px] text-foreground/60"
                >
                  <span className="shrink-0 text-red-400/70">-</span>
                  <span className="truncate">
                    {String(a.memo || a.contact || "")} -- $
                    {String(a.amount || "")}
                  </span>
                </div>
              ))}
              {(item.count || 0) > (item.sample?.length || 0) && (
                <p className="text-[10px] text-foreground/40 italic">
                  +{(item.count || 0) - (item.sample?.length || 0)} more...
                </p>
              )}
            </div>
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
  const isDone = event.type === "workflow_done" || event.type === "workflow_complete";

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
          <ActorBadge actor={event.actor} />
          <span className="text-[10px] text-foreground/45 tabular-nums">
            {formatTime(event.timestamp)}
          </span>
        </div>
        <p
          className={`text-xs leading-relaxed ${
            isError
              ? "text-red-400/80"
              : isDone
                ? "text-emerald-400/80 font-medium"
                : "text-foreground/80"
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
      </div>
    </div>
  );
}

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

const STEP_BAR_COLORS: Record<string, string> = {
  running: "bg-blue-400 animate-pulse",
  completed: "bg-emerald-400",
  failed: "bg-red-400",
  skipped: "bg-foreground/15",
  pending: "bg-foreground/[0.08]",
};

function RunCard({ run }: { run: TrackedRun }) {
  const [expanded, setExpanded] = useState(run.status === "paused");
  const [acting, setActing] = useState(false);

  const handleApprove = useCallback(
    async (approve: boolean) => {
      setActing(true);
      try {
        await approveWorkflowRun(run.runId, approve);
      } catch (err) {
        logger.error("workflow_approval_action_failed", {
          runId: run.runId,
          approve,
          error: err instanceof Error ? err.message : String(err),
        });
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
    } catch (err) {
      logger.error("workflow_cancel_action_failed", {
        runId: run.runId,
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setActing(false);
    }
  }, [run.runId]);

  const isTerminal = run.status === "completed" || run.status === "failed";

  return (
    <div
      className={`rounded-xl ring-1 overflow-hidden transition-all ${
        run.status === "paused"
          ? "ring-amber-400/20 bg-amber-400/[0.04]"
          : isTerminal
            ? "ring-foreground/[0.06] bg-foreground/[0.02] opacity-60"
            : "ring-foreground/[0.08] bg-foreground/[0.03]"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left"
      >
        {expanded ? (
          <ChevronDown size={11} className="text-foreground/50 shrink-0" />
        ) : (
          <ChevronRight size={11} className="text-foreground/50 shrink-0" />
        )}
        {run.status === "paused" ? (
          <Pause size={11} className="text-amber-400 shrink-0" />
        ) : run.status === "completed" ? (
          <CheckCircle2 size={11} className="text-emerald-400 shrink-0" />
        ) : run.status === "failed" ? (
          <XCircle size={11} className="text-red-400 shrink-0" />
        ) : (
          <Loader2
            size={11}
            className="animate-spin text-blue-400 shrink-0"
          />
        )}
        <span className="text-xs font-medium text-foreground/80 truncate flex-1">
          {run.name}
        </span>
        <span
          className={`text-[10px] font-medium shrink-0 ${
            run.status === "paused"
              ? "text-amber-400/80"
              : run.status === "completed"
                ? "text-emerald-400/80"
                : run.status === "failed"
                  ? "text-red-400/80"
                  : "text-blue-400/80"
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
        <div className="border-t border-foreground/[0.06] px-3 py-2.5 space-y-2.5">
          <div className="flex items-center gap-0.5">
            {run.steps.map((step) => (
              <div
                key={step.id}
                className={`h-1 flex-1 rounded-full ${STEP_BAR_COLORS[step.status] || STEP_BAR_COLORS.pending}`}
                title={`${step.id}: ${step.status}`}
              />
            ))}
          </div>

          {run.status === "paused" && (
            <div className="space-y-2.5">
              {run.approvalPrompt && (
                <p className="text-[11px] text-amber-400/70 leading-relaxed">
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
                  className="inline-flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-emerald-400 disabled:opacity-50 shadow-sm"
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
                  className="inline-flex items-center gap-1 rounded-lg bg-foreground/[0.06] px-3 py-1.5 text-[11px] font-medium text-foreground/70 hover:text-foreground hover:bg-foreground/[0.1] disabled:opacity-50"
                >
                  <X size={10} />
                  Reject
                </button>
              </div>
            </div>
          )}

          {isTerminal && run.completionMessage && (
            <p className={`text-[11px] leading-relaxed ${
              run.status === "completed"
                ? "text-emerald-400/70"
                : "text-red-400/70"
            }`}>
              {run.completionMessage}
            </p>
          )}

          {run.status === "running" && (
            <button
              onClick={handleCancel}
              disabled={acting}
              className="inline-flex items-center gap-1 rounded-lg bg-foreground/[0.06] px-3 py-1.5 text-[11px] font-medium text-foreground/60 hover:text-foreground/80 hover:bg-foreground/[0.1] disabled:opacity-50"
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
    <div className="px-3 py-3 space-y-2.5 border-b border-foreground/[0.06] shrink-0">
      {active.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-foreground/50 uppercase tracking-wider">
            Active runs
          </p>
          {active.map((run) => (
            <RunCard key={run.runId} run={run} />
          ))}
        </div>
      )}
      {terminal.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-foreground/50 uppercase tracking-wider">
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
          {events.length > 0 && (
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
          Gateway & Lobster events
        </p>
      </div>

      <WorkflowRunsSection events={events} />

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {events.length === 0 ? (
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
            {events.map((event, i) => (
              <EventRow key={`${event.timestamp}-${i}`} event={event} />
            ))}
          </div>
        )}
      </div>

      {events.length > 0 && (
        <div className="border-t border-foreground/[0.06] px-4 py-2 flex items-center justify-between text-[10px] text-foreground/45">
          <span>{events.length} events</span>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1">
              <span className="h-1 w-1 rounded-full bg-blue-400/60" />
              Gateway: {events.filter((e) => e.actor === "gateway").length}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-1 w-1 rounded-full bg-foreground/30" />
              Lobster: {events.filter((e) => e.actor === "lobster").length}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
