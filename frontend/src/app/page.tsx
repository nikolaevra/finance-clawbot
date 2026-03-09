import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase-server";
import AppShell from "@/components/AppShell";
import StarterHome from "@/components/StarterHome";

export const dynamic = "force-dynamic";

function getDisplayName(user: { email?: string | null; user_metadata?: unknown }) {
  const metadata =
    user.user_metadata && typeof user.user_metadata === "object"
      ? (user.user_metadata as Record<string, unknown>)
      : {};

  const fromMetadata =
    (typeof metadata.full_name === "string" && metadata.full_name) ||
    (typeof metadata.name === "string" && metadata.name) ||
    null;

  if (fromMetadata) return fromMetadata;
  if (user.email) return user.email.split("@")[0];
  return null;
}

export default async function Home() {
  const supabase = await createServerSupabase();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const displayName = getDisplayName(user);

  return (
    <AppShell>
      <StarterHome withinShell userName={displayName} />
    </AppShell>
  );
}
