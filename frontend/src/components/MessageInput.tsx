"use client";

import { useState, useRef, useEffect } from "react";
import { ArrowUp } from "lucide-react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
    }
  }, [input]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const hasInput = input.trim().length > 0;

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="mx-auto max-w-2xl">
        <div className="flex items-end gap-3 rounded-2xl bg-foreground/[0.06] ring-1 ring-foreground/[0.08] px-4 py-3 shadow-lg shadow-black/10 focus-within:ring-foreground/[0.14] focus-within:bg-foreground/[0.08]">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none bg-transparent text-[14px] text-foreground/85 placeholder:text-foreground/25 focus:outline-none disabled:opacity-40 leading-relaxed"
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !hasInput}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all duration-200 ${
              hasInput && !disabled
                ? "bg-blue-500 text-white shadow-md shadow-blue-500/20 hover:bg-blue-400 scale-100"
                : "bg-foreground/[0.08] text-foreground/20 scale-95"
            } disabled:cursor-default`}
          >
            <ArrowUp size={16} strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>
  );
}
