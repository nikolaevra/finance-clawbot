"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Brain } from "lucide-react";

interface ThinkingIndicatorProps {
  thinking: string;
  isStreaming: boolean;
}

export default function ThinkingIndicator({ thinking, isStreaming }: ThinkingIndicatorProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  if (!thinking && !isStreaming) return null;
  return (
    <div className="mb-2">
      <button onClick={() => setIsExpanded(!isExpanded)} className="flex items-center gap-1.5 text-[11px] text-foreground/30 hover:text-foreground/50 transition-colors">
        <Brain size={12} strokeWidth={1.5} className={isStreaming ? "animate-pulse" : ""} />
        <span>{isStreaming ? "Thinking..." : "Thought process"}</span>
        {thinking && (isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />)}
      </button>
      {isExpanded && thinking && (
        <div className="mt-2 rounded-xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] p-3 text-xs leading-relaxed text-foreground/35 max-h-60 overflow-y-auto whitespace-pre-wrap">
          {thinking}
        </div>
      )}
    </div>
  );
}
