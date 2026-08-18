export type Severity = "OK" | "WARNING" | "CRITICAL" | "UNKNOWN";

export interface InstanceHealth {
  name: string;
  label: string;
  environment: string | null;
  reachable: boolean;
  overall_severity: Severity;
  categories: Record<string, Severity>;
  database_count: number | null;
  error: string | null;
}

export interface FleetHealth {
  overall_severity: Severity;
  instances: InstanceHealth[];
}

export interface DatabaseSummary {
  name: string;
  database_id: number;
  state: string;
}

export interface InstanceDetail {
  name: string;
  label: string;
  environment: string | null;
  databases: DatabaseSummary[];
}

// A tab's response is a map of section-key -> TabResult, e.g.
// { wait_stats: { data: [...rows], error: null } }. `data` shape depends on
// which MCP tool backs the section (see .claude/knowledge-base/_static/taxonomy.md).
export interface TabResult<T = Record<string, unknown>[]> {
  data: T | null;
  error: string | null;
}

export type TabResponse = Record<string, TabResult>;

export interface TrendPoint {
  captured_at: string;
  severity: Severity;
  metric_value: number | null;
}

export interface TrendResponse {
  points: TrendPoint[];
  available: boolean;
}

export interface Insight {
  instance_name: string;
  category: string;
  severity: Severity;
  message: string;
  created_at: string;
}

export type Role = "admin" | "member";

export interface InstanceSummary {
  name: string;
  label: string;
  environment: string | null;
}

export interface AppUser {
  username: string;
  role: Role;
  created_at: string;
}
