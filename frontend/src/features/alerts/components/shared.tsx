import type { ReactNode } from "react";
import { statusColorVar, tagStyle } from "../../../shared/styles/strata";
import type { Severity } from "../../../shared/types";
import type { AlertDefinition, AlertSetting, AlertTier } from "../types";

export const TIER_LABELS: Record<AlertTier, string> = { fast: "Every minute", standard: "Every 5 min", slow: "Hourly", daily: "Daily" };
export const SEVERITY_ORDER: Severity[] = ["CRITICAL", "WARNING", "UNKNOWN", "OK"];
const SEVERITY_LABEL: Record<Severity, string> = { CRITICAL: "Critical", WARNING: "Warning", UNKNOWN: "Unknown", OK: "OK" };

export function SeverityTag({ severity }: { severity: Severity }) {
  const color = severity === "UNKNOWN" ? "var(--muted)" : statusColorVar(severity);
  return <span className="tag" style={tagStyle(color)}>{SEVERITY_LABEL[severity]}</span>;
}

export const bySeverity = (a: Severity, b: Severity) => SEVERITY_ORDER.indexOf(a) - SEVERITY_ORDER.indexOf(b);

export function formatValue(value: number | null, unit: string | null | undefined) {
  if (value === null || value === undefined) return "";
  const text = Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return unit ? `${text} ${unit}` : text;
}

export function timeAgo(iso: string, now = Date.now()) {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export interface Effective {
  enabled: boolean;
  warning: number | null;
  critical: number | null;
  tier: AlertTier;
  confirm: number;
  excluded: string[];
}

/** Same inheritance as the backend: catalog default, then fleet row, then instance row. */
export function inherit(definition: AlertDefinition, rows: (AlertSetting | undefined)[]): Effective {
  const result: Effective = { enabled: definition.default_enabled, warning: definition.warning, critical: definition.critical,
    tier: definition.tier, confirm: definition.confirm_samples, excluded: [] };
  for (const row of rows) {
    if (!row) continue;
    if (row.enabled !== null) result.enabled = row.enabled;
    if (row.warning_threshold !== null) result.warning = row.warning_threshold;
    if (row.critical_threshold !== null) result.critical = row.critical_threshold;
    if (row.tier !== null) result.tier = row.tier;
    if (row.confirm_samples !== null) result.confirm = row.confirm_samples;
    result.excluded = [...result.excluded, ...(row.excluded_databases ?? [])];
  }
  return result;
}

/** One-line summary of what an alert does with its current settings. */
export function describeThresholds(definition: AlertDefinition, effective: Effective) {
  if (!definition.has_thresholds) return definition.kind === "event" ? "Each occurrence" : "Fixed severity";
  const sign = definition.direction === "above" ? "≥" : "≤";
  const parts = [];
  if (effective.warning !== null) parts.push(`warn ${sign} ${formatValue(effective.warning, definition.unit)}`);
  if (effective.critical !== null) parts.push(`crit ${sign} ${formatValue(effective.critical, definition.unit)}`);
  return parts.join(" · ");
}

export function EmptyPanel({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="panel-card alerts-empty"><strong>{title}</strong>{children && <span>{children}</span>}</div>;
}
