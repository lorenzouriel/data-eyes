import type { Severity } from "../../shared/types";
import type { ServerOverview } from "../instances/types";

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

