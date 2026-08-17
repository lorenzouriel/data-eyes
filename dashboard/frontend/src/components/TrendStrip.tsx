import { useEffect, useState } from "react";
import { getTrend } from "../api";
import type { Severity, TrendPoint } from "../types";

const SEVERITY_VAR: Record<Severity, string> = {
  OK: "var(--status-ok)",
  WARNING: "var(--status-warning)",
  CRITICAL: "var(--status-critical)",
  UNKNOWN: "var(--status-unknown)",
};

// Same icon glyphs as StatusBadge — the strip is a supplementary "at a
// glance" widget (the authoritative severity is always shown via a proper
// StatusBadge elsewhere on the same page), but per the dataviz skill's
// status-palette rule this legend keeps it from being color-alone even here.
const LEGEND: { severity: Severity; icon: string }[] = [
  { severity: "OK", icon: "●" },
  { severity: "WARNING", icon: "▲" },
  { severity: "CRITICAL", icon: "■" },
];

function formatPointTitle(p: TrendPoint): string {
  const when = new Date(p.captured_at).toLocaleString();
  const value = p.metric_value !== null ? ` (${p.metric_value.toFixed(1)})` : "";
  return `${when} — ${p.severity}${value}`;
}

export default function TrendStrip({
  instanceName,
  category,
  hours = 24,
  title,
}: {
  instanceName: string;
  category: string;
  hours?: number;
  title?: string;
}) {
  const [points, setPoints] = useState<TrendPoint[] | null>(null);
  const [available, setAvailable] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setPoints(null);
    getTrend(instanceName, category, hours)
      .then((res) => {
        if (cancelled) return;
        setPoints(res.points);
        setAvailable(res.available);
      })
      .catch(() => {
        if (cancelled) return;
        setPoints([]);
        setAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, [instanceName, category, hours]);

  // A secondary widget — no loading flash, it just appears once ready.
  if (points === null) return null;

  if (!available || points.length === 0) {
    return (
      <div className="trend-strip">
        {title && <div className="trend-strip-title">{title}</div>}
        <div className="trend-strip-empty">
          {available ? "Collecting history — check back shortly." : "Trend history unavailable."}
        </div>
      </div>
    );
  }

  return (
    <div className="trend-strip">
      {title && <div className="trend-strip-title">{title}</div>}
      <div className="trend-strip-bar" role="img" aria-label={`${category} severity over the last ${hours} hours`}>
        {points.map((p, i) => (
          <div key={i} className="trend-strip-segment" style={{ background: SEVERITY_VAR[p.severity] }} title={formatPointTitle(p)} />
        ))}
      </div>
      <div className="trend-strip-footer">
        <div className="trend-strip-legend">
          {LEGEND.map((l) => (
            <span key={l.severity} className="trend-strip-legend-item">
              <span style={{ color: SEVERITY_VAR[l.severity] }}>{l.icon}</span> {l.severity}
            </span>
          ))}
        </div>
        <span className="trend-strip-range">Last {hours}h</span>
      </div>
    </div>
  );
}
