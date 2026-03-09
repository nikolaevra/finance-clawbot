"use client";

import { useState } from "react";
import {
  ShieldAlert,
  Check,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Mail,
  Forward,
  Reply,
  Tag,
  Receipt,
  Send,
} from "lucide-react";
import type { PendingToolApproval } from "@/types";

const HIDDEN_TOOL_NAMES = new Set([
  "workflow_run",
  "workflow_status",
  "workflow_approve",
  "workflow_list",
]);

const TOOL_ICONS: Record<string, typeof Mail> = {
  gmail_send_message: Mail,
  gmail_reply_message: Reply,
  gmail_forward_message: Forward,
  gmail_modify_labels: Tag,
  accounting_create_bill: Receipt,
};

const GMAIL_TOOLS = new Set([
  "gmail_send_message",
  "gmail_reply_message",
  "gmail_forward_message",
]);

const ARG_DISPLAY_KEYS: Record<string, string[]> = {
  gmail_modify_labels: ["message_id", "add_label_ids"],
  accounting_create_bill: ["vendor_id", "line_items"],
};

function GmailPreview({ tc }: { tc: PendingToolApproval["toolCalls"][number] }) {
  const to = tc.args.to as string | undefined;
  const subject = tc.args.subject as string | undefined;
  const body = tc.args.body as string | undefined;
  const cc = tc.args.cc as string | undefined;
  const bcc = tc.args.bcc as string | undefined;
  const messageId = tc.args.message_id as string | undefined;

  const actionLabel =
    tc.name === "gmail_reply_message"
      ? "Reply"
      : tc.name === "gmail_forward_message"
        ? "Forward"
        : "New Message";

  return (
    <div className="rounded-xl overflow-hidden ring-1 ring-foreground/[0.08] bg-foreground/[0.02]">
      {/* Header bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-foreground/[0.04] border-b border-foreground/[0.06]">
        <Send size={12} className="text-blue-400/70" strokeWidth={1.5} />
        <span className="text-xs font-medium text-foreground/60">
          {actionLabel}
        </span>
      </div>

      {/* Fields */}
      <div className="divide-y divide-foreground/[0.05] text-[13px]">
        {to && (
          <div className="flex px-4 py-2">
            <span className="w-16 shrink-0 text-foreground/30 text-xs pt-0.5">To</span>
            <span className="text-foreground/70">{to}</span>
          </div>
        )}
        {cc && (
          <div className="flex px-4 py-2">
            <span className="w-16 shrink-0 text-foreground/30 text-xs pt-0.5">Cc</span>
            <span className="text-foreground/70">{cc}</span>
          </div>
        )}
        {bcc && (
          <div className="flex px-4 py-2">
            <span className="w-16 shrink-0 text-foreground/30 text-xs pt-0.5">Bcc</span>
            <span className="text-foreground/70">{bcc}</span>
          </div>
        )}
        {messageId && !to && (
          <div className="flex px-4 py-2">
            <span className="w-16 shrink-0 text-foreground/30 text-xs pt-0.5">Re</span>
            <span className="text-foreground/50 font-mono text-xs truncate">{messageId}</span>
          </div>
        )}
        {subject && (
          <div className="flex px-4 py-2">
            <span className="w-16 shrink-0 text-foreground/30 text-xs pt-0.5">Subject</span>
            <span className="text-foreground/80 font-medium">{subject}</span>
          </div>
        )}
      </div>

      {/* Body */}
      {body && (
        <div className="border-t border-foreground/[0.06] px-4 py-3">
          <p className="text-[13px] leading-relaxed text-foreground/60 whitespace-pre-wrap max-h-48 overflow-y-auto">
            {body}
          </p>
        </div>
      )}
    </div>
  );
}

interface ToolApprovalCardProps {
  approval: PendingToolApproval;
  onResolve: (approved: boolean) => void;
}

export function ToolApprovalCard({
  approval,
  onResolve,
}: ToolApprovalCardProps) {
  const [status, setStatus] = useState<
    "pending" | "approving" | "approved" | "rejected"
  >("pending");

  const handleAction = (approved: boolean) => {
    setStatus("approving");
    onResolve(approved);
    setStatus(approved ? "approved" : "rejected");
  };

  const visibleToolCalls = approval.toolCalls.filter(
    (tc) => !HIDDEN_TOOL_NAMES.has(tc.name)
  );

  if (status === "approved") {
    return (
      <div className="mx-4 my-2 rounded-2xl bg-emerald-400/[0.06] ring-1 ring-emerald-400/10 p-4">
        <div className="flex items-center gap-2 text-emerald-400/80">
          <CheckCircle2 size={15} strokeWidth={1.5} />
          <span className="text-sm font-medium">Action approved</span>
        </div>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="mx-4 my-2 rounded-2xl bg-red-400/[0.06] ring-1 ring-red-400/10 p-4">
        <div className="flex items-center gap-2 text-red-400/80">
          <XCircle size={15} strokeWidth={1.5} />
          <span className="text-sm font-medium">Action declined</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-4 my-2 rounded-2xl bg-background ring-1 ring-foreground/[0.08] shadow-md shadow-black/10 p-5 space-y-3">
      <div className="flex items-center gap-2">
        <ShieldAlert
          size={15}
          className="text-foreground/40"
          strokeWidth={1.5}
        />
        <span className="text-sm font-medium text-foreground/50">
          Approval Required
        </span>
      </div>

      <div className="space-y-2">
        {visibleToolCalls.length === 0 ? (
          <div className="rounded-xl bg-foreground/[0.03] ring-1 ring-foreground/[0.06] p-3.5">
            <p className="text-xs text-foreground/50">
              This action needs approval.
            </p>
          </div>
        ) : visibleToolCalls.map((tc) => {
          if (GMAIL_TOOLS.has(tc.name)) {
            return <GmailPreview key={tc.id} tc={tc} />;
          }

          const Icon = TOOL_ICONS[tc.name] ?? ShieldAlert;
          const displayKeys =
            ARG_DISPLAY_KEYS[tc.name] ?? Object.keys(tc.args).slice(0, 3);

          return (
            <div
              key={tc.id}
              className="rounded-xl bg-foreground/[0.03] ring-1 ring-foreground/[0.06] p-3.5 space-y-1.5"
            >
              <div className="flex items-center gap-2">
                <Icon
                  size={13}
                  className="text-foreground/40"
                  strokeWidth={1.5}
                />
                <span className="text-sm font-medium text-foreground/70">
                  {tc.label}
                </span>
              </div>
              <div className="text-xs text-foreground/40 space-y-0.5">
                {displayKeys.map((key) => {
                  const val = tc.args[key];
                  if (val === undefined || val === null || val === "")
                    return null;
                  const display =
                    typeof val === "string"
                      ? val.length > 80
                        ? val.slice(0, 80) + "..."
                        : val
                      : JSON.stringify(val).slice(0, 80);
                  return (
                    <div key={key}>
                      <span className="font-medium text-foreground/25">
                        {key}:
                      </span>{" "}
                      {display}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

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
          Decline
        </button>
      </div>
    </div>
  );
}
