"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function AutomationDetailAliasPage() {
  const router = useRouter();
  const params = useParams();
  const name = encodeURIComponent(String(params.name || ""));

  useEffect(() => {
    router.replace(`/chat/skills/${name}`);
  }, [name, router]);

  return null;
}
