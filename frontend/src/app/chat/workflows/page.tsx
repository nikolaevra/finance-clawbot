"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Workflow,
  PlayCircle,
  PauseCircle,
  Loader2,
  Clock,
  RefreshCw,
} from "lucide-react";
import type { WorkflowTemplate } from "@/types";
import { fetchWorkflowTemplates, triggerWorkflowRun } from "@/lib/api";
import { useActivity } from "@/components/ActivityProvider";

export default function WorkflowsPage() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const { togglePanel, isPanelOpen } = useActivity();

  const load = useCallback(async () => {
    try {
      const tpls = await fetchWorkflowTemplates();
      setTemplates(tpls);
    } catch {
      /* swallow */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleTrigger = async (templateId: string) => {
    setTriggeringId(templateId);
    try {
      await triggerWorkflowRun(templateId);
      if (!isPanelOpen) togglePanel();
    } catch {
      /* swallow */
    } finally {
      setTriggeringId(null);
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
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-500">
          <Workflow size={22} />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-zinc-800 dark:text-zinc-200">
            Workflows
          </h1>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Deterministic pipelines with approval gates
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      <div className="space-y-3">
        {templates.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-8 text-center">
            <Workflow
              size={32}
              className="mx-auto mb-2 text-zinc-300 dark:text-zinc-600"
            />
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No workflow templates available
            </p>
            <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
              Run the seed script to create built-in workflows
            </p>
          </div>
        ) : (
          templates.map((tpl) => (
            <div
              key={tpl.id}
              className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 p-4"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-zinc-800 dark:text-zinc-200 font-mono">
                      {tpl.name}
                    </h3>
                    {!tpl.user_id && (
                      <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-500">
                        System
                      </span>
                    )}
                  </div>
                  {tpl.description && (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      {tpl.description}
                    </p>
                  )}
                  <div className="flex items-center gap-3 mt-2 text-[11px] text-zinc-400">
                    <span>{tpl.steps.length} steps</span>
                    {tpl.schedule && (
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} />
                        Scheduled
                      </span>
                    )}
                    {tpl.steps.some((s) => s.approval?.required) && (
                      <span className="inline-flex items-center gap-1 text-amber-500">
                        <PauseCircle size={10} />
                        Has approval gates
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleTrigger(tpl.id)}
                  disabled={triggeringId === tpl.id}
                  className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {triggeringId === tpl.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <PlayCircle size={12} />
                  )}
                  Run
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
