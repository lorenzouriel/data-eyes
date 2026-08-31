import type { Severity } from "../types";
import { statusColorVar, statusLabel, tagStyle } from "../strata";

// Status is never carried by color alone: a dot plus a text label, never
// just a hue — same accessibility rule the previous design followed, kept
// through the Strata re-skin.
export default function StatusBadge({ severity, label }: { severity: Severity; label?: string }) {
  const color = statusColorVar(severity);
  return (
    <span className="tag" style={{ display: "inline-flex", alignItems: "center", gap: 6, ...tagStyle(color) }}>
      <span className="status-dot" style={{ background: color, width: 6, height: 6 }} aria-hidden="true" />
      {label ? `${label}: ${statusLabel(severity)}` : statusLabel(severity)}
    </span>
  );
}
