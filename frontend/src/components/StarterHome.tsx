"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { MoonStar, Sunrise, Sun, Sunset, type LucideIcon } from "lucide-react";
import { createConversation } from "@/lib/api";

interface StarterHomeProps {
  withinShell?: boolean;
  userName?: string | null;
}

type DaySegment = "morning" | "afternoon" | "evening" | "night";

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
      router.push(`/chat/${conversation.id}?${query.toString()}`);
    } catch {
      setError("Unable to start a new conversation. Please try again.");
      setIsSubmitting(false);
    }
  };

  const containerClass = withinShell
    ? "flex-1 bg-background flex items-center justify-center p-4"
    : "min-h-screen bg-background flex items-center justify-center p-4";

  return (
    <main className={containerClass}>
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-2xl rounded-2xl border border-foreground/[0.12] bg-background px-4 py-4 shadow-sm"
      >
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400">
            <GreetingIcon size={20} strokeWidth={1.8} />
          </div>
          <div>
            <p className="text-xl font-semibold text-foreground">{greeting}</p>
            <p className="text-xs text-foreground/45">
              Finance AI Assistant · {timeZone}
            </p>
          </div>
        </div>
        <p className="mb-3 text-sm text-foreground/60">
          Start a new finance conversation
        </p>
        <div className="flex items-center gap-2">
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Ask your Finance AI Assistant anything..."
            className="h-12 flex-1 rounded-xl border border-foreground/[0.12] bg-background px-4 text-sm text-foreground outline-none transition-colors focus:border-foreground/30"
            disabled={isSubmitting}
          />
          <button
            type="submit"
            disabled={isSubmitting || !prompt.trim()}
            className="h-12 rounded-xl border border-foreground/[0.12] px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-foreground/[0.06] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </form>
    </main>
  );
}
