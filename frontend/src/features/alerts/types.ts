export type AlertTier = "fast" | "standard" | "slow" | "daily";
export type AlertSeverity = "OK" | "WARNING" | "CRITICAL" | "UNKNOWN";

export interface AlertDefinition {
  key: string;
  name: string;
  group: string;
  kind: "state" | "event";
  tier: AlertTier;
  description: string;
  unit: string | null;
  direction: "above" | "below";
  warning: number | null;
  critical: number | null;
  default_enabled: boolean;
  confirm_samples: number;
  permission: string;
  per_database: boolean;
  scope: "instance" | "data_eyes";
  has_thresholds: boolean;
}

// One saved override. instance_name "" is the fleet-wide row; null fields inherit.
export interface AlertSetting {
  alert_key: string;
  instance_name: string;
  enabled: boolean | null;
  warning_threshold: number | null;
  critical_threshold: number | null;
  tier: AlertTier | null;
  confirm_samples: number | null;
  excluded_databases: string[] | null;
}

export interface AlertCatalog {
  alerts: AlertDefinition[];
  tiers: Record<AlertTier, number>;
  settings: AlertSetting[];
}

export interface AlertState {
  instance_name: string;
  alert_key: string;
  severity: AlertSeverity;
  observed_severity: AlertSeverity;
  streak: number;
  metric_value: number | null;
  detail: string;
  status: "ok" | "error";
  status_message: string;
  checked_at: string;
  changed_at: string;
}

export interface AlertEvent {
  alert_event_id: number;
  instance_name: string;
  alert_key: string;
  severity: "WARNING" | "CRITICAL";
  occurred_at: string;
  captured_at: string;
  metric_value: number | null;
  detail: string;
}

export interface DigestSetting {
  enabled: boolean;
  hour_utc: number;
  channel_ids: number[];
  last_sent_on?: string | null;
}
