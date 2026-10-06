import { useEffect, useState } from "react";
import { getInstanceTab } from "../api";
import type { TabResponse } from "../types";

/** Fetches one instance-tab's sections (GET /api/instances/:name/tabs/:tab)
 * and re-fetches whenever the instance/tab/database changes. */
export function useInstanceTab(instanceName: string, tabName: string, database?: string, refreshMs?: number) {
  const [data, setData] = useState<TabResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => getInstanceTab(instanceName, tabName, database)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load tab");
          setLoading(false);
        }
      }).finally(() => {
        if (!cancelled && refreshMs) timer = setTimeout(refresh, refreshMs);
      });
    refresh();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [instanceName, tabName, database, refreshMs]);

  return { data, loading, error };
}
