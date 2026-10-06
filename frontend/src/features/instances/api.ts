import { request } from "../../shared/api/client";
import type { TabResponse, TrendResponse, InstanceSummary, InstanceOverview, ActivityDimension, TopDimensionResponse, DimensionLogResponse } from "./types";

export function getInstanceOverview(instanceName: string) {
  return request<InstanceOverview>(`/api/instances/${encodeURIComponent(instanceName)}/overview`);
}

export function getInstanceTab(instanceName: string, tabName: string, database?: string) {
  const query = database ? `?database=${encodeURIComponent(database)}` : "";
  return request<TabResponse>(
    `/api/instances/${encodeURIComponent(instanceName)}/tabs/${encodeURIComponent(tabName)}${query}`,
  );
}

export function getTrend(instanceName: string, category: string, hours = 24) {
  return request<TrendResponse>(
    `/api/instances/${encodeURIComponent(instanceName)}/trend/${encodeURIComponent(category)}?hours=${hours}`,
  );
}

// --- Top-N historical activity (routers/activity.py) ---

export function getTopDimension(instanceName: string, dimension: ActivityDimension, range: "30d" | "7d" = "30d", limit = 10) {
  return request<TopDimensionResponse>(
    `/api/instances/${encodeURIComponent(instanceName)}/top/${encodeURIComponent(dimension)}?range=${range}&limit=${limit}`,
  );
}

export function getDimensionLog(instanceName: string, dimension: ActivityDimension, day: string) {
  return request<DimensionLogResponse>(
    `/api/instances/${encodeURIComponent(instanceName)}/top/${encodeURIComponent(dimension)}/log?day=${encodeURIComponent(day)}`,
  );
}

// --- Instance registry (any logged-in user can manage these — one shared
// team, see app/modules/auth/router.py's docstring for the tenancy model) ---

export function getInstances() {
  return request<InstanceSummary[]>("/api/instances");
}

export function createInstance(input: {
  name: string;
  label: string;
  environment?: string;
  connection_string: string;
}) {
  return request<InstanceSummary>("/api/instances", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateInstance(
  name: string,
  input: { label?: string; environment?: string; clear_environment?: boolean; connection_string?: string },
) {
  return request<InstanceSummary>(`/api/instances/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function deleteInstance(name: string) {
  return request<void>(`/api/instances/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export interface TestConnectionResult {
  ok: boolean;
  message: string;
}

// Tries a connection string before it's saved. `instanceName` is passed for
// the Edit form: when the connection-string field is left blank (keep the
// current one), the backend falls back to the already-registered string.
export function testConnection(connectionString: string, instanceName?: string) {
  const path = instanceName
    ? `/api/instances/${encodeURIComponent(instanceName)}/test-connection`
    : "/api/instances/test-connection";
  return request<TestConnectionResult>(path, {
    method: "POST",
    body: JSON.stringify({ connection_string: connectionString || undefined }),
  });
}

