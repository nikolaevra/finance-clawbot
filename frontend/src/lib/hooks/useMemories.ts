"use client";

import { useState, useEffect, useCallback } from "react";
import type { MemoryListResponse } from "@/types";
import { fetchMemories } from "@/lib/api";

export function useMemories() {
  const [memories, setMemories] = useState<MemoryListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchMemories();
      setMemories(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load memories"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  return { memories, loading, error, refresh };
}
