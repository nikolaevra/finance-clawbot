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
        <Loader2 className="h-5 w-5 animate-spin text-foreground/20" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-6 pb-24 md:pb-6">
      <div className="flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-400/10">
          <Sparkles size={20} className="text-blue-400" strokeWidth={1.5} />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-foreground/85 tracking-tight">
            Skills
          </h1>
          <p className="text-xs text-foreground/30">
            User-defined capabilities the AI can activate
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 rounded-xl ring-1 ring-foreground/[0.08] px-3 py-1.5 text-xs font-medium text-foreground/40 hover:text-foreground/60 hover:bg-foreground/[0.06]"
          >
            <RefreshCw size={12} strokeWidth={1.5} />
            Refresh
          </button>
          <button
            onClick={() => setShowNewForm(true)}
            className="flex items-center gap-1.5 rounded-xl bg-blue-500 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-blue-400 shadow-sm shadow-blue-500/20"
          >
            <Plus size={12} strokeWidth={1.5} />
            New Skill
          </button>
        </div>
      </div>

      {showNewForm && (
        <div className="mb-5 rounded-2xl bg-blue-400/[0.04] ring-1 ring-blue-400/10 p-5">
          <h3 className="text-sm font-medium text-foreground/75 mb-3">
            Create New Skill
          </h3>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="skill-name (lowercase, hyphens)"
              className="flex-1 rounded-xl bg-foreground/[0.06] ring-1 ring-foreground/[0.08] px-4 py-2 text-sm text-foreground/85 outline-none focus:ring-foreground/[0.2] placeholder:text-foreground/20"
              autoFocus
            />
            <button
              onClick={handleCreate}
              disabled={creating}
              className="rounded-xl bg-blue-500 px-4 py-2 text-xs font-medium text-white hover:bg-blue-400 disabled:opacity-50"
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
              className="rounded-xl ring-1 ring-foreground/[0.08] px-4 py-2 text-xs font-medium text-foreground/40 hover:text-foreground/60 hover:bg-foreground/[0.06]"
            >
              Cancel
            </button>
          </div>
          {newError && (
            <p className="mt-2.5 text-xs text-red-400/80">
              {newError}
            </p>
          )}
        </div>
      )}

      <div className="space-y-3">
        {skills.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-foreground/[0.08] p-10 text-center">
            <Sparkles
              size={28}
              className="mx-auto mb-3 text-foreground/10"
              strokeWidth={1.5}
            />
            <p className="text-sm text-foreground/35">
              No skills created yet
            </p>
            <p className="text-xs text-foreground/20 mt-1">
              Skills are markdown files that teach the AI new capabilities
            </p>
          </div>
        ) : (
          skills.map((skill) => (
            <div
              key={skill.id}
              className="rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] p-5 transition-all hover:bg-foreground/[0.06]"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-foreground/75 font-mono">
                      {skill.name}
                    </h3>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                        skill.enabled
                          ? "bg-emerald-400/10 text-emerald-400/80"
                          : "bg-foreground/[0.06] text-foreground/30"
                      }`}
                    >
                      {skill.enabled ? "Active" : "Disabled"}
                    </span>
                  </div>
                  {skill.description && (
                    <p className="text-xs text-foreground/35 mt-1.5">
                      {skill.description}
                    </p>
                  )}
                  <p className="text-[11px] text-foreground/20 mt-2">
                    Updated{" "}
                    {new Date(skill.updated_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleToggle(skill.name, skill.enabled)}
                    disabled={togglingId === skill.name}
                    className="p-2 rounded-lg text-foreground/25 hover:text-foreground/50 hover:bg-foreground/[0.06] disabled:opacity-50"
                    title={skill.enabled ? "Disable" : "Enable"}
                  >
                    {togglingId === skill.name ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : skill.enabled ? (
                      <ToggleRight
                        size={15}
                        className="text-emerald-400/80"
                      />
                    ) : (
                      <ToggleLeft size={15} />
                    )}
                  </button>
                  <button
                    onClick={() =>
                      router.push(
                        `/chat/skills/${encodeURIComponent(skill.name)}`
                      )
                    }
                    className="p-2 rounded-lg text-foreground/25 hover:text-foreground/50 hover:bg-foreground/[0.06]"
                    title="Edit"
                  >
                    <Pencil size={14} strokeWidth={1.5} />
                  </button>
                  <button
                    onClick={() => handleDelete(skill.name)}
                    disabled={deletingName === skill.name}
                    className="p-2 rounded-lg text-foreground/25 hover:text-red-400 hover:bg-red-400/10 disabled:opacity-50"
                    title="Delete"
                  >
                    {deletingName === skill.name ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Trash2 size={14} strokeWidth={1.5} />
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
