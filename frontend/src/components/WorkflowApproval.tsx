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
      <div className="mx-4 my-2 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-900/20 p-4">
        <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 size={16} />
          <span className="text-sm font-medium">Workflow approved and resuming</span>
        </div>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="mx-4 my-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/20 p-4">
        <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
          <XCircle size={16} />
          <span className="text-sm font-medium">Workflow rejected and cancelled</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-4 my-2 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <PauseCircle size={16} className="text-amber-600 dark:text-amber-400" />
        <span className="text-sm font-medium text-amber-700 dark:text-amber-300">
          Workflow Approval Required
        </span>
        <span className="ml-auto text-xs text-amber-600/70 dark:text-amber-400/70 font-mono">
          {workflowName}
        </span>
      </div>
      <p className="text-sm text-zinc-700 dark:text-zinc-300 mb-3">
        {prompt}
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleAction(true)}
          disabled={status === "approving"}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
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
          className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-200 dark:bg-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 transition-colors hover:bg-zinc-300 dark:hover:bg-zinc-600 disabled:opacity-50"
        >
          <X size={12} />
          Reject
        </button>
      </div>
    </div>
  );
}

const STATUS_CONFIG = {
  pending: { icon: Loader2, color: "text-zinc-500", label: "Pending", animate: true },
  running: { icon: PlayCircle, color: "text-blue-500", label: "Running", animate: false },
  paused: { icon: PauseCircle, color: "text-amber-500", label: "Awaiting Approval", animate: false },
  completed: { icon: CheckCircle2, color: "text-emerald-500", label: "Completed", animate: false },
  failed: { icon: AlertTriangle, color: "text-red-500", label: "Failed", animate: false },
  cancelled: { icon: XCircle, color: "text-zinc-400", label: "Cancelled", animate: false },
} as const;

interface WorkflowStatusBadgeProps {
  status: keyof typeof STATUS_CONFIG;
}

export function WorkflowStatusBadge({ status }: WorkflowStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${config.color}`}>
      <Icon size={12} className={config.animate ? "animate-spin" : ""} />
      {config.label}
    </span>
  );
}
