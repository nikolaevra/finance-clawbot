"use client";

import { useRef, useEffect, useState } from "react";
import { ArrowUp, Check, ChevronDown, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Skill } from "@/types";

interface MessageInputProps {
  onSend: (
    message: string,
    options?: { forcedSkill?: string }
  ) => void;
  disabled: boolean;
  value: string;
  onChange: (value: string) => void;
  skills: Skill[];
  skillsLoading: boolean;
  selectedSkillName: string | null;
  onSelectSkill: (skillName: string | null) => void;
}

export default function MessageInput({
  onSend,
  disabled,
  value,
  onChange,
  skills,
  skillsLoading,
  selectedSkillName,
  onSelectSkill,
}: MessageInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [skillsOpen, setSkillsOpen] = useState(false);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
    }
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, { forcedSkill: selectedSkillName ?? undefined });
    onChange("");
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

  const hasInput = value.trim().length > 0;
  const selectedSkill = skills.find((skill) => skill.name === selectedSkillName);

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="mx-auto max-w-2xl">
        <div className="rounded-[1.6rem] border border-foreground/[0.12] bg-background px-4 pb-3 pt-3 shadow-lg shadow-black/8 transition-colors focus-within:border-foreground/[0.2]">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={disabled}
            rows={1}
            className="max-h-[200px] min-h-[56px] w-full resize-none bg-transparent text-[15px] text-foreground/90 placeholder:text-foreground/35 focus:outline-none disabled:opacity-40 leading-relaxed"
          />
          <div className="mt-2.5 flex items-center justify-between">
            <Popover open={skillsOpen} onOpenChange={setSkillsOpen}>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 rounded-full px-2.5 text-xs text-blue-500 hover:bg-blue-500/10 hover:text-blue-500"
                  disabled={disabled}
                >
                  <Sparkles size={13} />
                  <span className="max-w-[12rem] truncate">
                    {selectedSkill ? selectedSkill.name : "Skills"}
                  </span>
                  <ChevronDown size={12} />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                side="top"
                align="start"
                className="w-[18rem] rounded-xl border-foreground/[0.12] p-1.5"
              >
                <button
                  type="button"
                  onClick={() => {
                    onSelectSkill(null);
                    setSkillsOpen(false);
                  }}
                  className="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm text-foreground/80 transition-colors hover:bg-foreground/[0.06]"
                >
                  <span>Default (no skill)</span>
                  {!selectedSkillName ? <Check size={14} className="text-blue-500" /> : null}
                </button>
                {skillsLoading ? (
                  <p className="px-2.5 py-2 text-xs text-foreground/45">Loading skills...</p>
                ) : skills.length > 0 ? (
                  skills.map((skill) => (
                    <button
                      key={skill.id}
                      type="button"
                      onClick={() => {
                        onSelectSkill(skill.name);
                        setSkillsOpen(false);
                      }}
                      className="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm text-foreground/80 transition-colors hover:bg-foreground/[0.06]"
                    >
                      <span className="truncate">{skill.name}</span>
                      {selectedSkillName === skill.name ? (
                        <Check size={14} className="text-blue-500" />
                      ) : null}
                    </button>
                  ))
                ) : (
                  <p className="px-2.5 py-2 text-xs text-foreground/45">No active skills found</p>
                )}
              </PopoverContent>
            </Popover>

            <Button
              type="button"
              onClick={handleSubmit}
              disabled={disabled || !hasInput}
              size="icon-sm"
              className="h-8 w-8 rounded-full bg-foreground/10 text-foreground/45 hover:bg-foreground/15 hover:text-foreground/80 disabled:opacity-60 data-[enabled=true]:bg-blue-500 data-[enabled=true]:text-white data-[enabled=true]:hover:bg-blue-400"
              data-enabled={hasInput && !disabled}
            >
              <ArrowUp size={16} strokeWidth={2} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
