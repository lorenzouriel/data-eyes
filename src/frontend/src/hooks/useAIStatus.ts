import { useEffect, useState } from "react";
import { getAIStatus } from "../api";
import type { AIStatus } from "../types";

export function useAIStatus() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getAIStatus()
      .then((value) => active && setStatus(value))
      .catch(() => active && setStatusError("AI provider status is unavailable."));
    return () => {
      active = false;
    };
  }, []);

  return { status, statusError };
}
