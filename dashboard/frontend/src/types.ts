export type Severity = "OK" | "WARNING" | "CRITICAL" | "UNKNOWN";

export interface InstanceHealth {
  name: string;
  label: string;
  environment: string | null;
  reachable: boolean;
  overall_severity: Severity;
  categories: Record<string, Severity>;
  metrics: Record<string, number>;
  database_count: number | null;
  error: string | null;
}

export interface FleetHealth {
  overall_severity: Severity;
  instances: InstanceHealth[];
}

// A tab's response is a map of section-key -> TabResult, e.g.
// { wait_stats: { data: [...rows], error: null } }. `data` shape depends on
// which diagnostics.py function backs the section (see
// .claude/knowledge-base/_static/taxonomy.md).
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

// --- Advisor + Ask the fleet (app/insights_agent.py) ---

export interface AdvisorTimelineStep {
  stage: string;
  detail: string;
}

export interface AdvisorFinding {
  finding_key: string;
  title: string;
  severity: string;
  timeline: AdvisorTimelineStep[];
  proposed_ddl: string | null;
  risks: string[];
  evidence: string[];
  estimated_impact: string | null;
}

export interface AdvisorReport {
  summary: string;
  findings: AdvisorFinding[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
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

// --- Strata instance-tabs shapes (app/routers/instance_tabs.py) ---

export interface ServerOverview {
  ProductVersion?: string;
  Edition?: string;
  MachineName?: string;
  Cores?: number;
  TotalMemoryGB?: number;
  TotalDiskGB?: number;
}

export interface InstanceOverview {
  server: TabResult<ServerOverview>;
  health: TabResult<{ overall_severity: Severity; categories: Record<string, Severity>; metrics: Record<string, number> }>;
}

export interface WaitStatRow {
  Wait_Type: string;
  Wait_Time_Seconds: number;
  Waiting_Tasks_Count: number;
  Percentage_WaitTime: number;
  Category: string;
  severity: Severity;
}

export interface WaitCategoryPoint {
  captured_at: string;
  category: string;
  seconds: number;
}

export interface BlockingRow {
  BlockedSessionID: number;
  BlockingSessionID: number;
  WaitType: string;
  WaitTimeSeconds: number;
  WaitResource: string;
  DatabaseName: string;
  BlockedLoginName: string;
  BlockedHostName: string;
  BlockedQueryText: string;
  BlockingSessionIsHeadBlocker: number;
  severity: Severity;
}

export interface BlockingEvent {
  captured_at: string;
  root_sql: string | null;
  lock_type: string | null;
  blocked_count: number;
  duration_seconds: number;
}

export interface SessionRow {
  Pid: number;
  SqlText: string;
  LoginName: string;
  ProgramName: string;
  HostName: string;
  State: string;
  WaitSeconds: number;
  ElapsedSeconds: number;
}

export interface SessionDimensions {
  users: { Dimension: string; WaitSeconds: number }[];
  programs: { Dimension: string; WaitSeconds: number }[];
  hosts: { Dimension: string; WaitSeconds: number }[];
}

export interface TopQueryRow {
  DatabaseName: string;
  PlanHandle: string;
  ExecutionCount: number;
  AvgElapsedTimeMs: number;
  AvgCpuTimeMs: number;
  AvgLogicalReads: number;
  MaxElapsedTimeMs: number;
  LastExecutionTime: string;
  QueryText: string;
  severity: Severity;
}

export interface PlanNode {
  depth: number;
  physical_op: string;
  logical_op: string;
  estimated_rows: string | null;
  cost_share: number;
  estimated_time_ms: number;
}

export interface QueryPlan {
  available: boolean;
  execution_count?: number;
  avg_elapsed_ms?: number;
  avg_logical_reads?: number;
  nodes: PlanNode[];
}

export interface AGHealthRow {
  DatabaseName: string;
  Replica: string;
  SyncState: string;
  SyncHealth: string;
  IsPrimaryReplica: boolean;
  LogSendQueueKB: number;
  RedoQueueKB: number;
  severity: Severity;
}

export interface ResourceUtilization {
  buffer_cache_hit_pct: number | null;
  page_life_expectancy_seconds: number | null;
  cpu_history: { TimestampMs: number; CpuPct: number }[];
  disk_read_bytes_total: number | null;
  batch_requests_total: number | null;
}
