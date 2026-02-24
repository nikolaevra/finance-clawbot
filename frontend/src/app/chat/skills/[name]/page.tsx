"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  Save,
  Check,
  Loader2,
  Trash2,
  Wrench,
} from "lucide-react";
import {
  fetchSkill,
  updateSkill,
  deleteSkill,
  fetchToolCatalog,
} from "@/lib/api";
import type { ToolCatalogEntry } from "@/types";

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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-sm text-zinc-500">
          Skill &quot;{skillName}&quot; not found.
        </p>
        <button
          onClick={() => router.push("/chat/skills")}
          className="text-sm text-violet-500 hover:underline"
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
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/chat/skills")}
            className="rounded-lg p-1.5 text-zinc-500 dark:text-zinc-400 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-zinc-700 dark:hover:text-zinc-200"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 font-mono">
              {skillName}
            </h1>
            <p className="text-xs text-zinc-500">SKILL.md</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <span className="text-xs text-red-500 dark:text-red-400">
              {error}
            </span>
          )}
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
          >
            <Trash2 size={12} />
            Delete
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              saved
                ? "bg-green-600/20 text-green-600 dark:text-green-400"
                : "bg-zinc-200 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 hover:bg-zinc-300 dark:hover:bg-zinc-700"
            }`}
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : saved ? (
              <Check size={14} />
            ) : (
              <Save size={14} />
            )}
            {saving ? "Saving..." : saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Editor */}
        <div className="flex flex-1 flex-col">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 resize-none bg-white dark:bg-zinc-950 p-4 font-mono text-sm text-zinc-800 dark:text-zinc-200 outline-none placeholder:text-zinc-400 dark:placeholder:text-zinc-600"
            placeholder="---\nname: my-skill\ndescription: What this skill does\nenabled: true\n---\n\n# Skill Instructions\n\n..."
            spellCheck={false}
          />
        </div>

        {/* Tool catalog sidebar */}
        <div className="hidden md:block w-72 shrink-0 border-l border-zinc-200 dark:border-zinc-800 overflow-y-auto">
          <div className="p-3">
            <div className="flex items-center gap-1.5 mb-3">
              <Wrench size={12} className="text-zinc-500" />
              <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Available Tools
              </h2>
            </div>
            <p className="text-[11px] text-zinc-400 dark:text-zinc-600 mb-3">
              Reference these tools in your skill instructions.
            </p>

            {toolsLoading ? (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <Loader2 size={12} className="animate-spin" />
                Loading...
              </div>
            ) : (
              <div className="space-y-4">
                {Object.entries(toolsByCategory).map(([category, catTools]) => (
                  <div key={category}>
                    <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-600 mb-1.5">
                      {category}
                    </h3>
                    <div className="space-y-1">
                      {catTools.map((tool) => (
                        <div
                          key={tool.name}
                          className="rounded-lg px-2 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-900"
                        >
                          <p className="text-xs font-mono font-medium text-zinc-700 dark:text-zinc-300">
                            {tool.name}
                          </p>
                          <p className="text-[10px] text-zinc-500 dark:text-zinc-500 leading-tight mt-0.5">
                            {tool.description.length > 80
                              ? tool.description.slice(0, 80) + "..."
                              : tool.description}
                          </p>
                        </div>
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
