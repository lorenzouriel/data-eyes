
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
  // Re-send while a state alert stays open ("alert without clear").
  renotify_seconds?: number | null;
  // Stay silent on the change; notify once the alert has been open this long.
  escalate_after_seconds?: number | null;
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
  event: {
    kind?: "transition" | "event" | "reminder" | "digest";
    title?: string | null;
    old_severity: string | null;
    new_severity: string;
    metric_value: number | null;
  };
}

