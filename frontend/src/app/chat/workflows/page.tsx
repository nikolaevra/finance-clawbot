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
        <Loader2 className="h-5 w-5 animate-spin text-foreground/20" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-6 pb-24 md:pb-6">
      <div className="flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-400/10">
          <Workflow size={20} className="text-blue-400" strokeWidth={1.5} />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-foreground/85 tracking-tight">
            Workflows
          </h1>
          <p className="text-xs text-foreground/30">
            Deterministic pipelines with approval gates
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 rounded-xl ring-1 ring-foreground/[0.08] px-3 py-1.5 text-xs font-medium text-foreground/40 hover:text-foreground/60 hover:bg-foreground/[0.06]"
        >
          <RefreshCw size={12} strokeWidth={1.5} />
          Refresh
        </button>
      </div>

      <div className="space-y-3">
        {templates.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-foreground/[0.08] p-10 text-center">
            <Workflow
              size={28}
              className="mx-auto mb-3 text-foreground/10"
              strokeWidth={1.5}
            />
            <p className="text-sm text-foreground/35">
              No workflow templates available
            </p>
            <p className="text-xs text-foreground/20 mt-1">
              Run the seed script to create built-in workflows
            </p>
          </div>
        ) : (
          templates.map((tpl) => (
            <div
              key={tpl.id}
              className="rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] p-5 transition-all hover:bg-foreground/[0.06]"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-foreground/75 font-mono">
                      {tpl.name}
                    </h3>
                    {!tpl.user_id && (
                      <span className="rounded-full bg-blue-400/10 px-2 py-0.5 text-[10px] font-medium text-blue-400/70">
                        System
                      </span>
                    )}
                  </div>
                  {tpl.description && (
                    <p className="text-xs text-foreground/35 mt-1.5">
                      {tpl.description}
                    </p>
                  )}
                  <div className="flex items-center gap-3 mt-2.5 text-[11px] text-foreground/25">
                    <span>{tpl.steps.length} steps</span>
                    {tpl.schedule && (
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} strokeWidth={1.5} />
                        Scheduled
                      </span>
                    )}
                    {tpl.steps.some((s) => s.approval?.required) && (
                      <span className="inline-flex items-center gap-1 text-amber-400/60">
                        <PauseCircle size={10} strokeWidth={1.5} />
                        Has approval gates
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleTrigger(tpl.id)}
                  disabled={triggeringId === tpl.id}
                  className="shrink-0 inline-flex items-center gap-1.5 rounded-xl bg-blue-500 px-4 py-2 text-xs font-medium text-white hover:bg-blue-400 shadow-sm shadow-blue-500/20 disabled:opacity-50"
                >
                  {triggeringId === tpl.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <PlayCircle size={12} strokeWidth={1.5} />
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
