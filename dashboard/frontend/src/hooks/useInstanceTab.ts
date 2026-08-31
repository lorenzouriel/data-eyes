import { useEffect, useState } from "react";
import { getInstanceTab } from "../api";
import type { TabResponse } from "../types";

/** Fetches one instance-tab's sections (GET /api/instances/:name/tabs/:tab)
 * and re-fetches whenever the instance/tab/database changes. */
export function useInstanceTab(instanceName: string, tabName: string, database?: string) {
  const [data, setData] = useState<TabResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getInstanceTab(instanceName, tabName, database)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load tab");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [instanceName, tabName, database]);

  return { data, loading, error };
}
