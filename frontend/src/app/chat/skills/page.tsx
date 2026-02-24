"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  Plus,
  Loader2,
  RefreshCw,
  ToggleLeft,
  ToggleRight,
  Trash2,
  Pencil,
} from "lucide-react";
import { useSkills } from "@/lib/hooks/useSkills";
import {
  createSkill,
  deleteSkill,
  toggleSkill as apiToggleSkill,
} from "@/lib/api";

const DEFAULT_SKILL_TEMPLATE = `---
name: my-new-skill
description: Describe what this skill does
enabled: true
---

# My New Skill

When the user asks to [describe the trigger]:

1. Use the \`tool_name\` tool to...
2. Then...
3. Finally, respond with...
`;

export default function SkillsPage() {
  const router = useRouter();
  const { skills, loading, refresh } = useSkills();
  const [creating, setCreating] = useState(false);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newError, setNewError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const handleCreate = async () => {
    const name = newName.trim().toLowerCase().replace(/\s+/g, "-");
    if (!name) {
      setNewError("Name is required.");
      return;
    }
    setCreating(true);
    setNewError(null);
    try {
      const content = DEFAULT_SKILL_TEMPLATE.replace("my-new-skill", name)
        .replace("My New Skill", name.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
      await createSkill(name, content);
      setShowNewForm(false);
      setNewName("");
      refresh();
      router.push(`/chat/skills/${encodeURIComponent(name)}`);
    } catch (err) {
      setNewError(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setCreating(false);
    }
  };

  const handleToggle = async (skillName: string, currentEnabled: boolean) => {
    setTogglingId(skillName);
    try {
      await apiToggleSkill(skillName, !currentEnabled);
      refresh();
    } catch {
      /* swallow */
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (skillName: string) => {
    if (!confirm(`Delete skill "${skillName}"? This cannot be undone.`)) return;
    setDeletingName(skillName);
    try {
      await deleteSkill(skillName);
      refresh();
    } catch {
      /* swallow */
    } finally {
      setDeletingName(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 pb-24 md:pb-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-500">
          <Sparkles size={22} />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-zinc-800 dark:text-zinc-200">
            Skills
          </h1>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            User-defined capabilities the AI can activate
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
          <button
            onClick={() => setShowNewForm(true)}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 transition-colors"
          >
            <Plus size={12} />
            New Skill
          </button>
        </div>
      </div>

      {/* New skill form */}
      {showNewForm && (
        <div className="mb-4 rounded-xl border border-violet-200 dark:border-violet-800/50 bg-violet-50/50 dark:bg-violet-950/20 p-4">
          <h3 className="text-sm font-medium text-zinc-800 dark:text-zinc-200 mb-2">
            Create New Skill
          </h3>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="skill-name (lowercase, hyphens)"
              className="flex-1 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 outline-none focus:border-violet-400 dark:focus:border-violet-500 placeholder:text-zinc-400 dark:placeholder:text-zinc-600"
              autoFocus
            />
            <button
              onClick={handleCreate}
              disabled={creating}
              className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 transition-colors disabled:opacity-50"
            >
              {creating ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                "Create"
              )}
            </button>
            <button
              onClick={() => {
                setShowNewForm(false);
                setNewName("");
                setNewError(null);
              }}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              Cancel
            </button>
          </div>
          {newError && (
            <p className="mt-2 text-xs text-red-500 dark:text-red-400">
              {newError}
            </p>
          )}
        </div>
      )}

      {/* Skills list */}
      <div className="space-y-3">
        {skills.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-8 text-center">
            <Sparkles
              size={32}
              className="mx-auto mb-2 text-zinc-300 dark:text-zinc-600"
            />
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No skills created yet
            </p>
            <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
              Skills are markdown files that teach the AI new capabilities
            </p>
          </div>
        ) : (
          skills.map((skill) => (
            <div
              key={skill.id}
              className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 p-4"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-zinc-800 dark:text-zinc-200 font-mono">
                      {skill.name}
                    </h3>
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                        skill.enabled
                          ? "bg-green-500/10 text-green-600 dark:text-green-400"
                          : "bg-zinc-200 dark:bg-zinc-800 text-zinc-500"
                      }`}
                    >
                      {skill.enabled ? "Active" : "Disabled"}
                    </span>
                  </div>
                  {skill.description && (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      {skill.description}
                    </p>
                  )}
                  <p className="text-[11px] text-zinc-400 mt-1.5">
                    Updated{" "}
                    {new Date(skill.updated_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    onClick={() => handleToggle(skill.name, skill.enabled)}
                    disabled={togglingId === skill.name}
                    className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
                    title={skill.enabled ? "Disable" : "Enable"}
                  >
                    {togglingId === skill.name ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : skill.enabled ? (
                      <ToggleRight
                        size={16}
                        className="text-green-500"
                      />
                    ) : (
                      <ToggleLeft size={16} />
                    )}
                  </button>
                  <button
                    onClick={() =>
                      router.push(
                        `/chat/skills/${encodeURIComponent(skill.name)}`
                      )
                    }
                    className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                    title="Edit"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => handleDelete(skill.name)}
                    disabled={deletingName === skill.name}
                    className="p-1.5 rounded-lg text-zinc-500 hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-500 transition-colors disabled:opacity-50"
                    title="Delete"
                  >
                    {deletingName === skill.name ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Trash2 size={16} />
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
