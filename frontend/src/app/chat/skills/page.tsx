"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  Plus,
  Loader2,
  RefreshCw,
  Play,
  Trash2,
  Pencil,
} from "lucide-react";
import { useSkills } from "@/lib/hooks/useSkills";
import {
  createSkill,
  createConversation,
  deleteSkill,
  toggleSkill as apiToggleSkill,
} from "@/lib/api";
import type { Skill } from "@/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const DEFAULT_SKILL_TEMPLATE = `---
name: my-new-skill
description: Describe what this skill does
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
  const [testingName, setTestingName] = useState<string | null>(null);

  const WEEK_DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const formatScheduleSummary = (skill: Skill): string | null => {
    if (!skill.schedule_enabled) return null;

    const timePart = skill.schedule_time || "time not set";
    const timezonePart = skill.schedule_timezone || "UTC";

    if (skill.schedule_type === "weekly") {
      const days = Array.isArray(skill.schedule_days)
        ? skill.schedule_days
            .filter((d) => d >= 0 && d <= 6)
            .sort((a, b) => a - b)
            .map((d) => WEEK_DAY_LABELS[d])
        : [];
      const dayPart = days.length > 0 ? days.join(", ") : "no weekdays selected";
      return `Weekly schedule on ${dayPart} at ${timePart} (${timezonePart})`;
    }

    return `Daily schedule at ${timePart} (${timezonePart})`;
  };

  const formatTriggerSummary = (skill: Skill): string | null => {
    if (!skill.trigger_enabled) return null;

    const providerPart =
      skill.trigger_provider === "gmail" ? "Gmail" : "Unknown provider";
    const eventPart =
      skill.trigger_event === "new_email" ? "new email" : "custom event";
    const filters = (skill.trigger_filters || {}) as Record<string, unknown>;
    const filterParts: string[] = [];

    if (filters.inbox_only !== false) {
      filterParts.push("inbox only");
    }
    if (typeof filters.from_contains === "string" && filters.from_contains.trim()) {
      filterParts.push(`from contains "${filters.from_contains.trim()}"`);
    }
    if (
      typeof filters.subject_contains === "string" &&
      filters.subject_contains.trim()
    ) {
      filterParts.push(`subject contains "${filters.subject_contains.trim()}"`);
    }

    return filterParts.length > 0
      ? `${providerPart} ${eventPart} trigger (${filterParts.join(", ")})`
      : `${providerPart} ${eventPart} trigger`;
  };

  const formatUpdatedDate = (value: string): string => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Unknown";
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatLatestRun = (skill: Skill): string => {
    const scheduleKey = (skill.last_scheduled_run_key || "").trim();
    const triggerKey = (skill.last_trigger_event_key || "").trim();

    let scheduleDate: Date | null = null;
    const scheduleMatch = scheduleKey.match(
      /^(\d{4})-(\d{2})-(\d{2}):([0-2]\d):([0-5]\d):(daily|weekly)$/
    );
    if (scheduleMatch) {
      const [, year, month, day, hour, minute] = scheduleMatch;
      const parsed = new Date(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour),
        Number(minute)
      );
      if (!Number.isNaN(parsed.getTime())) {
        scheduleDate = parsed;
      }
    }

    let triggerDate: Date | null = null;
    if (triggerKey) {
      const parsed = new Date(triggerKey);
      if (!Number.isNaN(parsed.getTime())) {
        triggerDate = parsed;
      }
    }

    const latest =
      scheduleDate && triggerDate
        ? scheduleDate > triggerDate
          ? scheduleDate
          : triggerDate
        : scheduleDate || triggerDate;
    if (latest) {
      return latest.toLocaleString();
    }
    if (scheduleKey || triggerKey) {
      return "Recorded";
    }
    return "Never";
  };

  const formatAutomationDetail = (skill: Skill): string => {
    const scheduleSummary = formatScheduleSummary(skill);
    const triggerSummary = formatTriggerSummary(skill);
    if (triggerSummary && scheduleSummary) {
      return `${triggerSummary} • ${scheduleSummary}`;
    }
    return triggerSummary || scheduleSummary || "Manual only";
  };

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

  const handleTryAutomation = async (skillName: string) => {
    setTestingName(skillName);
    try {
      const conversation = await createConversation(`Try: ${skillName}`);
      const prompt = `Run the "${skillName}" automation now and show me the result.`;
      router.push(
        `/chat/${encodeURIComponent(conversation.id)}?q=${encodeURIComponent(prompt)}&skill=${encodeURIComponent(skillName)}`
      );
    } catch {
      /* swallow */
    } finally {
      setTestingName(null);
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
    <div className="w-full px-6 py-6 pb-24 md:pb-6">
      <div className="flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-400/10">
          <Sparkles size={20} className="text-blue-400" strokeWidth={1.5} />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-foreground/85 tracking-tight">
            Automations
          </h1>
          <p className="text-xs text-foreground/30">
            Plain-text automation instructions with optional schedule and triggers
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
            New Automation
          </button>
        </div>
      </div>

      {showNewForm && (
        <div className="mb-5 rounded-2xl bg-blue-400/[0.04] ring-1 ring-blue-400/10 p-5">
          <h3 className="text-sm font-medium text-foreground/75 mb-3">
            Create New Automation
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
              Automations are markdown instructions the AI can run manually, on schedule, or on triggers
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-foreground/[0.08] bg-card/70">
            <Table>
              <TableHeader>
                <TableRow className="border-foreground/[0.08]">
                  <TableHead className="px-4 text-xs text-foreground/45">Automation</TableHead>
                  <TableHead className="text-xs text-foreground/45">Enabled</TableHead>
                  <TableHead className="text-xs text-foreground/45">Latest run</TableHead>
                  <TableHead className="text-xs text-foreground/45">Updated</TableHead>
                  <TableHead className="text-right text-xs text-foreground/45">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.map((skill) => (
                  <TableRow key={skill.id} className="border-foreground/[0.06]">
                    <TableCell className="px-4 py-3 align-top">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-foreground">{skill.name}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-foreground/50">
                          {formatAutomationDetail(skill)}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="py-3 align-top">
                      <div className="inline-flex min-w-24 items-center">
                        {togglingId === skill.name ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-foreground/[0.04] px-2.5 py-1 text-xs text-foreground/65 ring-1 ring-foreground/[0.14]">
                            <Loader2 size={12} className="animate-spin" />
                            Saving
                          </span>
                        ) : (
                          <select
                            value={skill.enabled ? "enabled" : "disabled"}
                            onChange={(event) => {
                              const nextEnabled = event.target.value === "enabled";
                              if (nextEnabled !== skill.enabled) {
                                void handleToggle(skill.name, skill.enabled);
                              }
                            }}
                            className={`h-8 rounded-full px-2.5 text-xs font-medium ring-1 outline-none transition-colors ${
                              skill.enabled
                                ? "bg-emerald-500/10 text-emerald-400 ring-emerald-400/30"
                                : "bg-foreground/[0.04] text-foreground/60 ring-foreground/[0.14]"
                            }`}
                            aria-label={`Set ${skill.name} status`}
                          >
                            <option value="enabled">Enabled</option>
                            <option value="disabled">Disabled</option>
                          </select>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="py-3 text-xs text-foreground/70">{formatLatestRun(skill)}</TableCell>
                    <TableCell className="py-3 text-xs text-foreground/70">
                      {formatUpdatedDate(skill.updated_at)}
                    </TableCell>
                    <TableCell className="py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleTryAutomation(skill.name)}
                          disabled={testingName === skill.name}
                          className="rounded-lg p-2 text-foreground/35 hover:bg-blue-400/10 hover:text-blue-400/90 disabled:opacity-50"
                          title="Try automation"
                        >
                          {testingName === skill.name ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Play size={14} strokeWidth={1.5} />
                          )}
                        </button>
                        <button
                          onClick={() =>
                            router.push(
                              `/chat/skills/${encodeURIComponent(skill.name)}`
                            )
                          }
                          className="rounded-lg p-2 text-foreground/35 hover:bg-foreground/[0.06] hover:text-foreground/65"
                          title="Edit"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => handleDelete(skill.name)}
                          disabled={deletingName === skill.name}
                          className="rounded-lg p-2 text-foreground/35 hover:bg-red-400/10 hover:text-red-400 disabled:opacity-50"
                          title="Delete"
                        >
                          {deletingName === skill.name ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Trash2 size={14} strokeWidth={1.5} />
                          )}
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
