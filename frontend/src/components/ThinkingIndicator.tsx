"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Brain } from "lucide-react";

interface ThinkingIndicatorProps {
  thinking: string;
  isStreaming: boolean;
}

export default function ThinkingIndicator({
  thinking,
  isStreaming,
}: ThinkingIndicatorProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!thinking && !isStreaming) return null;

  return (
    <div className="mb-2">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-400 transition-colors"
      >
        <Brain size={14} className={isStreaming ? "animate-pulse" : ""} />
        <span>{isStreaming ? "Thinking..." : "Thought process"}</span>
        {thinking &&
          (isExpanded ? (
            <ChevronDown size={12} />
          ) : (
            <ChevronRight size={12} />
          ))}
      </button>
      {isExpanded && thinking && (
        <div className="mt-1.5 rounded-lg bg-zinc-100 dark:bg-zinc-800/50 p-3 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400 max-h-60 overflow-y-auto whitespace-pre-wrap">
          {thinking}
        </div>
      )}
    </div>
  );
}
