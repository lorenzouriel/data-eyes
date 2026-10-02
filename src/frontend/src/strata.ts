import type { CSSProperties } from "react";
import type { Severity } from "./types";

// Strata's status color set (see styles.css's --status-* tokens) and its
// "tag" chip style (colored text on a soft matching background) — small
// shared helpers so every component builds these the same way, instead of
// re-deriving the color-mix math per component.

export function statusColorVar(severity: Severity): string {
  switch (severity) {
    case "CRITICAL":
      return "var(--status-crit)";
    case "WARNING":
      return "var(--status-warn)";
    case "OK":
      return "var(--status-ok)";
    default:
      return "var(--status-idle)";
  }
}

export function statusLabel(severity: Severity): string {
  switch (severity) {
    case "CRITICAL":
      return "Critical";
    case "WARNING":
      return "Warning";
    case "OK":
      return "Healthy";
    default:
      return "Unreachable";
  }
}

/** A colored-text-on-soft-background chip, matching the design's `tag()` helper. */
export function tagStyle(colorVar: string, bgMix = 13): CSSProperties {
  return {
    color: colorVar,
    background: `color-mix(in srgb, ${colorVar} ${bgMix}%, transparent)`,
  };
}

// Wait-category colors for the 4 coarse buckets app/diagnostics.py's
// categorize_wait_type() still recognizes by prefix (cpu, lock, disk,
// network). "other" is kept only as the color/label for wait-category
// history rows collected before that function stopped emitting it —
// anything categorize_wait_type() returns today is either one of these 4
// keys or a raw wait_type string, handled by colorForCategory/
// labelForCategory below rather than being forced into this fixed map.
export const CATEGORY_COLOR: Record<string, string> = {
  cpu: "#3b82f6",
  lock: "#e07a4a",
  disk: "#d9a318",
  network: "#7c8fa3",
  other: "#a9b0ba",
};

export const CATEGORY_LABEL: Record<string, string> = {
  cpu: "CPU / scheduler",
  lock: "Lock & latch",
  disk: "Disk IO",
  network: "Network / client",
  other: "Other",
};

// Rotating palette for wait types that fall outside the 4 known buckets —
// categorize_wait_type() surfaces those by their real name instead of
// lumping them into "other", so the chart needs a color per distinct wait
// type it actually sees, not just the 5 pre-defined ones.
const CATEGORY_PALETTE = [
  "#8b5cf6",
  "#10b981",
  "#ef4444",
  "#ec4899",
  "#14b8a6",
  "#f59e0b",
  "#6366f1",
  "#84cc16",
  "#06b6d4",
  "#f43f5e",
];

const _dynamicCategoryColors: Record<string, string> = {};
let _nextPaletteSlot = 0;

/** Stable color for any category — a known bucket's fixed color, or a
 * deterministically-assigned palette color for a raw wait_type name seen
 * for the first time. */
export function colorForCategory(category: string): string {
  if (CATEGORY_COLOR[category]) return CATEGORY_COLOR[category];
  if (!_dynamicCategoryColors[category]) {
    _dynamicCategoryColors[category] = CATEGORY_PALETTE[_nextPaletteSlot % CATEGORY_PALETTE.length];
    _nextPaletteSlot++;
  }
  return _dynamicCategoryColors[category];
}

/** Human label for any category — the friendly name for a known bucket, or
 * the raw wait_type itself (already a readable SQL Server identifier). */
export function labelForCategory(category: string): string {
  return CATEGORY_LABEL[category] ?? category;
}

// The 8 diagnostic categories app/diagnostics.py's fleet_health_score()
// computes, in its fixed insertion order — drives the Status Summary panel
// and the fleet table's per-category icon columns. Colored by severity
// (statusColorVar), not by category identity, so this is intentionally
// separate from CATEGORY_COLOR/colorForCategory above (those color wait-type
// buckets, a different axis entirely).
export const DIAGNOSTIC_CATEGORY_ORDER = [
  "wait_stats",
  "index_fragmentation",
  "db_space",
  "backup_health",
  "checkdb_health",
  "blocking",
  "ag_health",
  "job_health",
] as const;

export const DIAGNOSTIC_CATEGORY_LABEL: Record<string, string> = {
  wait_stats: "Wait time",
  index_fragmentation: "Index health",
  db_space: "Database space",
  backup_health: "Backups",
  checkdb_health: "CHECKDB",
  blocking: "Blocking",
  ag_health: "Availability groups",
  job_health: "SQL Agent jobs",
};

export const DIAGNOSTIC_CATEGORY_ABBR: Record<string, string> = {
  wait_stats: "WT",
  index_fragmentation: "IX",
  db_space: "SP",
  backup_health: "BK",
  checkdb_health: "CK",
  blocking: "BL",
  ag_health: "AG",
  job_health: "JB",
};

/** Known diagnostic categories first in fixed order, then anything
 * unrecognized (forward-compat if a 9th category is ever added), alphabetical. */
export function orderedCategories(categories: Record<string, unknown>): string[] {
  const known = DIAGNOSTIC_CATEGORY_ORDER.filter((c) => c in categories);
  const rest = Object.keys(categories)
    .filter((c) => !(DIAGNOSTIC_CATEGORY_ORDER as readonly string[]).includes(c))
    .sort();
  return [...known, ...rest];
}

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}d ago`;
}
