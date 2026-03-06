"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  Save,
  Check,
  Loader2,
  Trash2,
  Wrench,
  ShieldAlert,
} from "lucide-react";
import {
  fetchSkill,
  updateSkill,
  deleteSkill,
  fetchToolCatalog,
} from "@/lib/api";
import type { ToolCatalogEntry } from "@/types";

type ActiveMention = {
  start: number;
  end: number;
  query: string;
};

export function getActiveMentionAtCursor(
  text: string,
  cursor: number
): ActiveMention | null {
  if (cursor < 0 || cursor > text.length) return null;

  let atIndex = cursor - 1;
  while (atIndex >= 0 && /[a-z0-9_]/i.test(text[atIndex])) {
    atIndex -= 1;
  }

  if (atIndex < 0 || text[atIndex] !== "@") return null;
  if (atIndex > 0 && /[a-z0-9_]/i.test(text[atIndex - 1])) return null;

  let tokenEnd = cursor;
  while (tokenEnd < text.length && /[a-z0-9_]/i.test(text[tokenEnd])) {
    tokenEnd += 1;
  }

  const query = text.slice(atIndex + 1, cursor);
  if (!/^[a-z0-9_]*$/i.test(query)) return null;
  return { start: atIndex, end: tokenEnd, query };
}

export default function SkillEditorPage() {
  const router = useRouter();
  const params = useParams();
  const skillName = decodeURIComponent(params.name as string);

  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [tools, setTools] = useState<ToolCatalogEntry[]>([]);
  const [toolsLoading, setToolsLoading] = useState(true);
  const [activeMention, setActiveMention] = useState<ActiveMention | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await fetchSkill(skillName);
        if (!cancelled) setContent(data.content);
      } catch {
        if (!cancelled) setNotFound(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [skillName]);

  useEffect(() => {
    let cancelled = false;
    async function loadTools() {
      try {
        const data = await fetchToolCatalog();
        if (!cancelled) setTools(data);
      } catch {
        // best-effort
      } finally {
        if (!cancelled) setToolsLoading(false);
      }
    }
    loadTools();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await updateSkill(skillName, content);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }, [skillName, content]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSave]);

  const handleDelete = async () => {
    if (!confirm(`Delete skill "${skillName}"? This cannot be undone.`)) return;
    try {
      await deleteSkill(skillName);
      router.push("/chat/skills");
    } catch {
      setError("Failed to delete skill");
    }
  };

  const filteredMentionTools = useMemo(() => {
    if (!activeMention) return [];
    const query = activeMention.query.toLowerCase();
    if (!query) return tools;
    return tools.filter((tool) => tool.name.toLowerCase().startsWith(query));
  }, [activeMention, tools]);

  const refreshActiveMention = useCallback((text: string, cursor: number) => {
    setActiveMention(getActiveMentionAtCursor(text, cursor));
  }, []);

  useEffect(() => {
    setMentionIndex(0);
  }, [activeMention?.query]);

  useEffect(() => {
    if (filteredMentionTools.length === 0) setMentionIndex(0);
    else if (mentionIndex >= filteredMentionTools.length) setMentionIndex(0);
  }, [filteredMentionTools, mentionIndex]);

  const insertToolReference = useCallback(
    (toolName: string) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const mentionText = `@${toolName}`;
      const selectionStart = textarea.selectionStart ?? 0;
      const selectionEnd = textarea.selectionEnd ?? selectionStart;
      const mention = getActiveMentionAtCursor(content, selectionStart);

      const replaceStart = mention ? mention.start : selectionStart;
      const replaceEnd = mention ? mention.end : selectionEnd;
      const next =
        content.slice(0, replaceStart) + mentionText + content.slice(replaceEnd);
      const nextCursor = replaceStart + mentionText.length;

      setContent(next);
      setActiveMention(null);

      requestAnimationFrame(() => {
        textarea.focus();
        textarea.setSelectionRange(nextCursor, nextCursor);
      });
    },
    [content]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-5 w-5 animate-spin text-foreground/20" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-sm text-foreground/40">
          Skill &quot;{skillName}&quot; not found.
        </p>
        <button
          onClick={() => router.push("/chat/skills")}
          className="text-sm text-blue-400/80 hover:text-blue-400"
        >
          Back to skills
        </button>
      </div>
    );
  }

  const toolsByCategory = tools.reduce(
    (acc, tool) => {
      const cat = tool.category || "general";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(tool);
      return acc;
    },
    {} as Record<string, ToolCatalogEntry[]>
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-foreground/[0.06]">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/chat/skills")}
            className="rounded-lg p-1.5 text-foreground/30 hover:text-foreground/60 hover:bg-foreground/[0.06]"
          >
            <ArrowLeft size={16} strokeWidth={1.5} />
          </button>
          <div>
            <h1 className="text-sm font-medium text-foreground/80 font-mono">
              {skillName}
            </h1>
            <p className="text-[11px] text-foreground/25">SKILL.md</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <span className="text-xs text-red-400/80">
              {error}
            </span>
          )}
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 rounded-xl ring-1 ring-foreground/[0.08] px-3 py-1.5 text-xs font-medium text-red-400/70 hover:text-red-400 hover:bg-red-400/10"
          >
            <Trash2 size={12} strokeWidth={1.5} />
            Delete
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-sm font-medium transition-all ${
              saved
                ? "bg-emerald-400/10 text-emerald-400/80"
                : "bg-foreground/[0.06] text-foreground/60 hover:text-foreground/80 hover:bg-foreground/[0.1]"
            }`}
          >
            {saving ? (
              <Loader2 size={13} className="animate-spin" />
            ) : saved ? (
              <Check size={13} />
            ) : (
              <Save size={13} strokeWidth={1.5} />
            )}
            {saving ? "Saving..." : saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col">
          <div className="relative flex-1 min-h-0">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => {
              const next = e.target.value;
              setContent(next);
              refreshActiveMention(next, e.target.selectionStart ?? 0);
            }}
            onSelect={(e) => {
              const target = e.target as HTMLTextAreaElement;
              refreshActiveMention(content, target.selectionStart ?? 0);
            }}
            onClick={(e) => {
              const target = e.target as HTMLTextAreaElement;
              refreshActiveMention(content, target.selectionStart ?? 0);
            }}
            onKeyDown={(e) => {
              const dropdownOpen =
                !!activeMention && filteredMentionTools.length > 0;
              if (!dropdownOpen) return;

              if (e.key === "ArrowDown") {
                e.preventDefault();
                setMentionIndex((prev) =>
                  prev + 1 >= filteredMentionTools.length ? 0 : prev + 1
                );
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setMentionIndex((prev) =>
                  prev - 1 < 0 ? filteredMentionTools.length - 1 : prev - 1
                );
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                const selected = filteredMentionTools[mentionIndex];
                if (selected) insertToolReference(selected.name);
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                setActiveMention(null);
              }
            }}
            className="h-full w-full resize-none bg-transparent p-5 font-mono text-sm text-foreground/70 outline-none placeholder:text-foreground/15 leading-relaxed"
            placeholder="---\nname: my-skill\ndescription: What this skill does\nenabled: true\n---\n\n# Skill Instructions\n\n..."
            spellCheck={false}
          />
            {activeMention && filteredMentionTools.length > 0 && (
              <div className="absolute left-5 top-5 z-20 w-[22rem] max-h-56 overflow-y-auto rounded-xl border border-foreground/[0.08] bg-background/95 backdrop-blur shadow-2xl">
                {filteredMentionTools.map((tool, index) => (
                  <button
                    key={tool.name}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => insertToolReference(tool.name)}
                    className={`w-full px-3 py-2 text-left border-b border-foreground/[0.04] last:border-b-0 ${
                      index === mentionIndex
                        ? "bg-foreground/[0.08]"
                        : "hover:bg-foreground/[0.05]"
                    }`}
                  >
                    <p className="text-xs font-mono text-foreground/70">{tool.name}</p>
                    <p className="text-[10px] text-foreground/35 truncate">
                      {tool.description}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="hidden md:block w-72 shrink-0 border-l border-foreground/[0.06] overflow-y-auto">
          <div className="p-4">
            <div className="flex items-center gap-1.5 mb-3">
              <Wrench size={11} className="text-foreground/25" strokeWidth={1.5} />
              <h2 className="text-[11px] font-medium uppercase tracking-wider text-foreground/25">
                Available Tools
              </h2>
            </div>
            <p className="text-[11px] text-foreground/20 mb-4">
              Use <span className="font-mono">@tool_name</span> in your skill.
              Saving converts it to the canonical tool name.
            </p>

            {toolsLoading ? (
              <div className="flex items-center gap-2 text-xs text-foreground/25">
                <Loader2 size={12} className="animate-spin" />
                Loading...
              </div>
            ) : (
              <div className="space-y-5">
                {Object.entries(toolsByCategory).map(([category, catTools]) => (
                  <div key={category}>
                    <h3 className="text-[10px] font-semibold uppercase tracking-wider text-foreground/20 mb-2">
                      {category}
                    </h3>
                    <div className="space-y-0.5">
                      {catTools.map((tool) => (
                        <button
                          key={tool.name}
                          type="button"
                          onClick={() => insertToolReference(tool.name)}
                          className="w-full text-left rounded-lg px-2.5 py-2 hover:bg-foreground/[0.04]"
                        >
                          <div className="flex items-center gap-1.5">
                            <p className="text-xs font-mono font-medium text-foreground/50">
                              {tool.name}
                            </p>
                            {tool.requires_approval && (
                              <span
                                className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-medium bg-amber-400/10 text-amber-400/70"
                                title="Requires user approval before execution"
                              >
                                <ShieldAlert size={8} />
                                Approval
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-foreground/25 leading-tight mt-0.5">
                            {tool.description.length > 80
                              ? tool.description.slice(0, 80) + "..."
                              : tool.description}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
