"use client";

import { PauseCircle, Mail, MessageCircle, Smartphone } from "lucide-react";
import type { PendingExternalWait } from "@/types";

interface ExternalWaitCardProps {
  pendingWait: PendingExternalWait;
}

function channelIcon(channel: string) {
  switch (channel) {
    case "email":
      return Mail;
    case "sms":
    case "whatsapp":
      return Smartphone;
    default:
      return MessageCircle;
  }
}

export function ExternalWaitCard({ pendingWait }: ExternalWaitCardProps) {
  const channel = pendingWait.wait.channel || "external";
  const Icon = channelIcon(channel);
  return (
    <div className="mx-4 my-2 rounded-2xl bg-amber-400/[0.04] ring-1 ring-amber-400/15 p-5">
      <div className="flex items-center gap-2 mb-2">
        <PauseCircle size={15} className="text-amber-400/80" strokeWidth={1.5} />
        <span className="text-sm font-medium text-amber-400/80">Awaiting external response</span>
        <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-foreground/35">
          <Icon size={11} />
          {channel}
        </span>
      </div>
      <p className="text-sm text-foreground/55">
        {pendingWait.wait.message || "Execution paused until a matching inbound response is received."}
      </p>
      {pendingWait.wait.timeout_at ? (
        <p className="mt-2 text-xs text-foreground/35">Timeout: {pendingWait.wait.timeout_at}</p>
      ) : null}
    </div>
  );
}
