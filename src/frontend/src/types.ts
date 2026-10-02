export type Severity = "OK" | "WARNING" | "CRITICAL" | "UNKNOWN";

export interface CardCpu {
  sql_pct: number | null;
  os_pct: number | null;
  history: { TimestampMs: number; CpuPct: number }[];
}

export interface CardWorkers {
  MaxWorkers: number | null;
  CreatedWorkers: number | null;
  IdleWorkers: number | null;
}

export interface CardMemory {
  SqlMemoryKB: number | null;
  TargetMemoryKB: number | null;
  FreeMemoryKB: number | null;
  PageFaults: number | null;
}

export interface CardDrive {
  free_gb: number | null;
  io_bytes_per_sec?: number;
  latency_ms?: number;
}

export interface InstanceHealth {
  name: string;
  label: string;
  environment: string | null;
  reachable: boolean;
  overall_severity: Severity;
  categories: Record<string, Severity>;
  metrics: Record<string, number>;
  database_count: number | null;
  database_status?: {
    name: string;
    updateability: string | null;
    in_availability_group: boolean;
    availability_group: string | null;
    replica_role: string | null;
  }[] | null;
  error: string | null;
  // Fleet Cards data — best-effort, any of these can be null/absent even
  // when the instance is reachable (see health_score.py's read_card_extras).
  server?: ServerOverview | null;
  cpu?: CardCpu | null;
  workers?: CardWorkers | null;
  memory?: CardMemory | null;
  disk?: Record<string, CardDrive> | null;
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

export interface AIStatus {
  provider: "anthropic" | "openai" | "local" | string;
  provider_label: string;
  configured: boolean;
  routine_model: string;
  deep_model: string;
  base_url: string | null;
  reason: string | null;
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
// dimension was requested (see app/repository.py's get_dimension_log):
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
export type NotificationChannelType = "slack" | "teams" | "email" | "sms";
export interface NotificationChannel {
  id: number;
  name: string;
  type: NotificationChannelType;
  enabled: boolean;
  config: Record<string, string | number | boolean | string[]>;
}
export interface NotificationRule {
  id: number;
  name: string;
  channel_id: number;
  enabled: boolean;
  instance: string | null;
  category: string | null;
  severities: string[];
  recovery: boolean;
  cooldown_seconds: number | null;
  quiet_start: number | null;
  quiet_end: number | null;
  group_by_instance: boolean;
}
export interface NotificationLog {
  id: number;
  channel_id: number | null;
  rule_id: number | null;
  instance_name: string;
  category: string;
  status: "pending" | "sending" | "sent" | "failed" | "suppressed";
  message: string;
  attempts: number;
  created_at: string;
  event: { old_severity: string | null; new_severity: string; metric_value: number | null };
}
