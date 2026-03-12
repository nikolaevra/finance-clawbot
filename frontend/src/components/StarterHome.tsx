"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { MoonStar, Sunrise, Sun, Sunset, type LucideIcon } from "lucide-react";
import { createConversation, fetchInboxThreads } from "@/lib/api";
import type { EmailThread } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface StarterHomeProps {
  withinShell?: boolean;
  userName?: string | null;
}

type DaySegment = "morning" | "afternoon" | "evening" | "night";

const ONBOARDING_SKILL = "guided-onboarding-account-setup";

const STARTER_PROMPTS: Array<{ text: string; forcedSkill?: string }> = [
  {
    text: "Explain what you can do and guide me through onboarding plus account setup.",
    forcedSkill: ONBOARDING_SKILL,
  },
  {
    text: "Review my monthly spending and suggest 3 ways to reduce costs.",
  },
  {
    text: "Help me build a simple weekly budgeting plan I can follow.",
  },
];

function getDaySegment(hour: number): DaySegment {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 21) return "evening";
  return "night";
}

function getDaySegmentIcon(segment: DaySegment): LucideIcon {
  if (segment === "morning") return Sunrise;
  if (segment === "afternoon") return Sun;
  if (segment === "evening") return Sunset;
  return MoonStar;
}

export default function StarterHome({
  withinShell = false,
  userName,
}: StarterHomeProps) {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threads, setThreads] = useState<EmailThread[]>([]);
  const [isLoadingThreads, setIsLoadingThreads] = useState(true);
  const [inboxError, setInboxError] = useState<string | null>(null);
  const firstName = userName?.trim().split(/\s+/)[0] || null;

  const { daySegment, timeZone } = useMemo(() => {
    const resolvedTimeZone =
      Intl.DateTimeFormat().resolvedOptions().timeZone || "Local";
    const hourText = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      hour12: false,
      timeZone: resolvedTimeZone,
    }).format(new Date());
    const parsedHour = Number.parseInt(hourText, 10);
    const safeHour = Number.isNaN(parsedHour) ? new Date().getHours() : parsedHour;

    return {
      daySegment: getDaySegment(safeHour),
      timeZone: resolvedTimeZone,
    };
  }, []);

  const GreetingIcon = getDaySegmentIcon(daySegment);
  const greeting = firstName
    ? `Good ${daySegment}, ${firstName}`
    : `Good ${daySegment}`;

  useEffect(() => {
    let cancelled = false;

    async function loadInboxPreview() {
      setIsLoadingThreads(true);
      setInboxError(null);
      try {
        const data = await fetchInboxThreads("inbox", 1, 10);
        if (!cancelled) {
          setThreads(data.threads || []);
        }
      } catch (err) {
        if (!cancelled) {
          setInboxError(err instanceof Error ? err.message : "Failed to load inbox preview.");
          setThreads([]);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingThreads(false);
        }
      }
    }

    loadInboxPreview();

    return () => {
      cancelled = true;
    };
  }, []);

  const formatThreadTime = (value: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString();
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) return;

    setError(null);
    setIsSubmitting(true);

    try {
      const conversation = await createConversation("New Chat");
      const query = new URLSearchParams({ q: trimmedPrompt });
      const matchedStarter = STARTER_PROMPTS.find(
        (starter) => starter.text === trimmedPrompt
      );
      if (matchedStarter?.forcedSkill) {
        query.set("skill", matchedStarter.forcedSkill);
      }
      router.push(`/chat/${conversation.id}?${query.toString()}`);
    } catch {
      setError("Unable to start a new conversation. Please try again.");
      setIsSubmitting(false);
    }
  };

  const containerClass = withinShell
    ? "flex-1 bg-background overflow-y-auto"
    : "min-h-screen bg-background";

  return (
    <main className={containerClass}>
      <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-10">
        <form
          onSubmit={handleSubmit}
          className="w-full rounded-2xl border border-foreground/[0.12] bg-background px-4 py-4 shadow-sm md:px-5"
        >
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400">
              <GreetingIcon size={20} strokeWidth={1.8} />
            </div>
            <div>
              <p className="text-2xl font-semibold text-foreground">{greeting}</p>
              <p className="text-xs text-foreground/45">
                Finance AI Assistant · {timeZone}
              </p>
            </div>
          </div>
          <p className="mb-3 text-sm text-foreground/60">
            Start a new finance conversation
          </p>
          <div className="mb-3 flex flex-wrap gap-2">
            {STARTER_PROMPTS.map((starterPrompt) => (
              <Button
                key={starterPrompt.text}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPrompt(starterPrompt.text)}
                disabled={isSubmitting}
                className="h-auto rounded-full px-3 py-1.5 text-xs"
              >
                {starterPrompt.text}
              </Button>
            ))}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask your Finance AI Assistant anything..."
              className="h-12"
              disabled={isSubmitting}
            />
            <Button
              type="submit"
              disabled={isSubmitting || !prompt.trim()}
              className="h-12 px-6 sm:w-auto"
            >
              {isSubmitting ? "Sending..." : "Send"}
            </Button>
          </div>
          {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
        </form>

        <section className="mt-6 rounded-2xl border border-foreground/[0.12] bg-background p-4 shadow-sm md:p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-foreground">Inbox</h2>
            <p className="text-xs text-foreground/45">Showing latest 10 emails</p>
          </div>

          {isLoadingThreads ? (
            <p className="py-6 text-sm text-foreground/55">Loading recent emails...</p>
          ) : inboxError ? (
            <p className="py-6 text-sm text-red-500">{inboxError}</p>
          ) : threads.length === 0 ? (
            <p className="py-6 text-sm text-foreground/55">No inbox emails yet.</p>
          ) : (
            <div className="divide-y divide-foreground/[0.08] rounded-xl border border-foreground/[0.08]">
              {threads.map((thread) => (
                <button
                  key={thread.gmail_thread_id}
                  type="button"
                  onClick={() =>
                    router.push(
                      `/chat/inbox?emailId=${encodeURIComponent(thread.gmail_thread_id)}`
                    )
                  }
                  className="w-full px-3 py-3 text-left transition-colors hover:bg-foreground/[0.03] md:px-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="line-clamp-1 text-sm font-medium text-foreground">
                          {thread.subject_normalized || "(No subject)"}
                        </p>
                        {thread.has_unread && (
                          <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-blue-400" />
                        )}
                      </div>
                      <p className="mt-1 line-clamp-1 text-xs text-foreground/55">
                        {thread.ai_summary_preview || thread.snippet}
                      </p>
                    </div>
                    <p className="shrink-0 text-[11px] text-foreground/45">
                      {formatThreadTime(thread.last_message_internal_at)}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}

          <Button asChild variant="outline" className="mt-4 w-full">
            <Link href="/chat/inbox">Go to inbox to see more emails</Link>
          </Button>
        </section>
      </div>
    </main>
  );
}
