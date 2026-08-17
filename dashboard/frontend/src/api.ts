import type { FleetHealth, Insight, InstanceDetail, TabResponse, TrendResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function login(username: string, password: string) {
  return request<{ username: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

export function me() {
  return request<{ username: string }>("/api/auth/me");
}

export function getFleetHealth() {
  return request<FleetHealth>("/api/fleet");
}

export function getInstance(instanceName: string) {
  return request<InstanceDetail>(`/api/instances/${encodeURIComponent(instanceName)}`);
}

export function getDatabaseTab(instanceName: string, databaseName: string, tabName: string) {
  return request<TabResponse>(
    `/api/instances/${encodeURIComponent(instanceName)}/databases/${encodeURIComponent(databaseName)}/tabs/${encodeURIComponent(tabName)}`,
  );
}

export function getTrend(instanceName: string, category: string, hours = 24) {
  return request<TrendResponse>(
    `/api/instances/${encodeURIComponent(instanceName)}/trend/${encodeURIComponent(category)}?hours=${hours}`,
  );
}

export function getInsightsFeed() {
  return request<{ insights: Insight[] }>("/api/insights/feed");
}

// GET-based SSE streams — consumed via EventSource, so callers just need the
// URL (with credentials: EventSource takes withCredentials, not a fetch init).
export function fleetInsightStreamUrl() {
  return `${API_BASE}/api/insights/fleet/stream`;
}

export function tabInsightStreamUrl(instanceName: string, databaseName: string, tabName: string) {
  return `${API_BASE}/api/insights/instances/${encodeURIComponent(instanceName)}/databases/${encodeURIComponent(databaseName)}/tabs/${encodeURIComponent(tabName)}/stream`;
}

export interface ExplainRequest {
  instance_name: string;
  database_name?: string;
  tab_name?: string;
  question?: string;
}

// POST /api/insights/explain is also SSE, but EventSource can't send a POST
// body — so this parses the same "data: {json}\n\n" / "event: done\n..."
// framing by hand off a streamed fetch response.
export async function streamExplain(
  payload: ExplainRequest,
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/insights/explain`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, res.statusText);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      const parsed = JSON.parse(dataLine.slice("data: ".length));
      if (typeof parsed.text === "string") {
        onChunk(parsed.text);
      }
    }
  }
}
