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

// Wait-category colors, matching the design's C = {cpu, lock, io, net, other}
// palette — used by the Waits tab's stacked chart, legend, and table dots.
// Keyed by app/diagnostics.py's categorize_wait_type() bucket names.
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
