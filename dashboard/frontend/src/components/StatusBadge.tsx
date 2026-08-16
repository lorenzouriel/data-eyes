import type { Severity } from "../types";

// Status is never carried by color alone (dataviz skill, status-palette rule):
// each state gets a distinct icon shape AND a text label, not just a hue.
const SEVERITY_META: Record<Severity, { label: string; icon: string; className: string }> = {
  OK: { label: "Healthy", icon: "●", className: "status-ok" }, // ●
  WARNING: { label: "Warning", icon: "▲", className: "status-warning" }, // ▲
  CRITICAL: { label: "Critical", icon: "■", className: "status-critical" }, // ■
  UNKNOWN: { label: "Unreachable", icon: "?", className: "status-unknown" },
};

export default function StatusBadge({ severity, label }: { severity: Severity; label?: string }) {
  const meta = SEVERITY_META[severity] ?? SEVERITY_META.UNKNOWN;
  return (
    <span className={`status-badge ${meta.className}`}>
      <span className="status-badge-icon" aria-hidden="true">
        {meta.icon}
      </span>
      <span className="status-badge-text">{label ? `${label}: ${meta.label}` : meta.label}</span>
    </span>
  );
}
