import { request, streamSse } from "../../shared/api/client";
import type { AdvisorReport, ChatMessage, AIStatus } from "./types";

// --- Advisor + Ask the fleet (app/modules/insights/agent.py's structured/chat paths) ---

export function getAIStatus() {
  return request<AIStatus>("/api/insights/status");
}

export function getAdvisorReport(instanceName: string, database?: string) {
  const query = database ? `?database=${encodeURIComponent(database)}` : "";
  return request<AdvisorReport>(
    `/api/insights/instances/${encodeURIComponent(instanceName)}/advisor${query}`,
    { method: "POST" },
  );
}

export function dismissAdvisorFinding(instanceName: string, findingKey: string) {
  return request<{ ok: boolean }>(
    `/api/insights/instances/${encodeURIComponent(instanceName)}/advisor/dismiss`,
    { method: "POST", body: JSON.stringify({ finding_key: findingKey }) },
  );
}

export function streamAsk(messages: ChatMessage[], onChunk: (text: string) => void, signal?: AbortSignal): Promise<void> {
  return streamSse("/api/insights/ask", { messages }, onChunk, signal);
}

