import type { Severity } from "../../shared/types";

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

export interface InstanceSummary {
  name: string;
  label: string;
  environment: string | null;
}

// --- Strata instance-tabs shapes (app/modules/monitoring/instance_tabs_router.py) ---

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

// --- Top-N historical activity (routers/activity.py) ---

export type ActivityDimension =
  | "waits"
  | "programs"
  | "databases"
  | "machines"
  | "db_users"
  | "plans"
  | "sql_statements"
  | "files"
  | "drives"
  | "blocking_statements"
  | "deadlocks";

export interface TopDimensionPoint {
  day: string;
  value: number;
}

export interface TopDimensionSeries {
  key: string;
  label: string;
  points: TopDimensionPoint[];
}

export interface TopDimensionResponse {
  series: TopDimensionSeries[];
  other: TopDimensionPoint[];
  available: boolean;
}

// Raw drill-down rows for the Specific-Day view — shape depends on which
// dimension was requested (see app/modules/monitoring/repository.py's get_dimension_log):
// activity_sample-shaped for waits/programs/databases/machines/db_users/
// plans/sql_statements, file_io_snapshot-shaped for files/drives,
// blocking_event-shaped for blocking_statements, deadlock_event-shaped for
// deadlocks. Every field is optional since no single dimension populates them all.
export interface DimensionLogRow {
  captured_at?: string;
  occurred_at?: string;
  database_name?: string | null;
  program_name?: string | null;
  host_name?: string | null;
  login_name?: string | null;
  wait_type?: string | null;
  wait_category?: string | null;
  wait_time_ms?: number | null;
  elapsed_time_ms?: number | null;
  plan_handle?: string | null;
  sql_text?: string | null;
  file_name?: string | null;
  drive?: string | null;
  io_stall_ms?: number | null;
  root_sql?: string | null;
  lock_type?: string | null;
  blocked_count?: number | null;
  duration_seconds?: number | null;
  victim_login?: string | null;
  victim_host?: string | null;
  victim_program?: string | null;
  resource_description?: string | null;
  process_count?: number | null;
  summary?: string | null;
}

export interface DimensionLogResponse {
  rows: DimensionLogRow[];
  available: boolean;
}

export interface ResourceUtilization {
  buffer_cache_hit_pct: number | null;
  page_life_expectancy_seconds: number | null;
  cpu_history: { TimestampMs: number; CpuPct: number }[];
  disk_read_bytes_total: number | null;
  batch_requests_total: number | null;
}

