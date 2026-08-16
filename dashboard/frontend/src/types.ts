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
