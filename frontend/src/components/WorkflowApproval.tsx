"use client";

import { useState } from "react";
import { Check, X, Loader2, PlayCircle, PauseCircle, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { approveWorkflowRun } from "@/lib/api";

interface WorkflowApprovalProps {
  runId: string;
  workflowName: string;
  prompt: string;
  onResolved?: () => void;
}

export function WorkflowApprovalCard({
  runId,
  workflowName,
  prompt,
  onResolved,
}: WorkflowApprovalProps) {
  const [status, setStatus] = useState<"pending" | "approving" | "approved" | "rejected">("pending");

  const handleAction = async (approve: boolean) => {
    setStatus("approving");
    try {
      await approveWorkflowRun(runId, approve);
      setStatus(approve ? "approved" : "rejected");
      onResolved?.();
    } catch {
      setStatus("pending");
    }
  };

  if (status === "approved") {
    return (
      <div className="mx-4 my-2 rounded-2xl bg-emerald-400/[0.06] ring-1 ring-emerald-400/10 p-4">
        <div className="flex items-center gap-2 text-emerald-400/80">
          <CheckCircle2 size={15} strokeWidth={1.5} />
          <span className="text-sm font-medium">Workflow approved and resuming</span>
        </div>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="mx-4 my-2 rounded-2xl bg-red-400/[0.06] ring-1 ring-red-400/10 p-4">
        <div className="flex items-center gap-2 text-red-400/80">
          <XCircle size={15} strokeWidth={1.5} />
          <span className="text-sm font-medium">Workflow rejected and cancelled</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-4 my-2 rounded-2xl bg-amber-400/[0.04] ring-1 ring-amber-400/15 p-5">
      <div className="flex items-center gap-2 mb-3">
        <PauseCircle size={15} className="text-amber-400/80" strokeWidth={1.5} />
        <span className="text-sm font-medium text-amber-400/80">
          Workflow Approval Required
        </span>
        <span className="ml-auto text-[11px] text-foreground/25 font-mono">
          {workflowName}
        </span>
      </div>
      <p className="text-sm text-foreground/55 mb-4">
        {prompt}
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleAction(true)}
          disabled={status === "approving"}
          className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-400 shadow-sm shadow-emerald-500/20 disabled:opacity-50"
        >
          {status === "approving" ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Check size={12} />
          )}
          Approve
        </button>
        <button
          onClick={() => handleAction(false)}
          disabled={status === "approving"}
          className="inline-flex items-center gap-1.5 rounded-xl bg-foreground/[0.06] px-4 py-2 text-xs font-medium text-foreground/50 hover:text-foreground/70 hover:bg-foreground/[0.1] disabled:opacity-50"
        >
          <X size={12} />
          Reject
        </button>
      </div>
    </div>
  );
}

const STATUS_CONFIG = {
  pending: { icon: Loader2, color: "text-foreground/30", label: "Pending", animate: true },
  running: { icon: PlayCircle, color: "text-blue-400/80", label: "Running", animate: false },
  paused: { icon: PauseCircle, color: "text-amber-400/80", label: "Awaiting Approval", animate: false },
  completed: { icon: CheckCircle2, color: "text-emerald-400/80", label: "Completed", animate: false },
  failed: { icon: AlertTriangle, color: "text-red-400/80", label: "Failed", animate: false },
  cancelled: { icon: XCircle, color: "text-foreground/25", label: "Cancelled", animate: false },
} as const;

interface WorkflowStatusBadgeProps {
  status: keyof typeof STATUS_CONFIG;
}

export function WorkflowStatusBadge({ status }: WorkflowStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${config.color}`}>
      <Icon size={11} strokeWidth={1.5} className={config.animate ? "animate-spin" : ""} />
      {config.label}
    </span>
  );
}
