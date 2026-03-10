"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AutomationsPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/chat/skills");
  }, [router]);

  return null;
}
