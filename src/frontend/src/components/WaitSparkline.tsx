import { useEffect, useState } from "react";
import { getTrend } from "../api";
import { statusColorVar } from "../strata";
import type { TrendPoint } from "../types";

const MAX_BARS = 48;

const severityRank: Record<string, number> = {
  UNKNOWN: 0,
  OK: 1,
  WARNING: 2,
  CRITICAL: 3,
};

// A collector can produce more than a thousand points over 24 hours. Rendering
// every point with its own width and gap makes the row thousands of pixels wide.
// Keep the worst-severity point from each time bucket so alerts remain visible
// while the chart stays compact.
function compactPoints(points: TrendPoint[], limit = MAX_BARS): TrendPoint[] {
  if (points.length <= limit) return points;

  return Array.from({ length: limit }, (_, bucket) => {
    const start = Math.floor((bucket * points.length) / limit);
    const end = Math.max(start + 1, Math.floor(((bucket + 1) * points.length) / limit));
    return points.slice(start, end).reduce((selected, point) => {
      const pointRank = severityRank[point.severity] ?? 0;
      const selectedRank = severityRank[selected.severity] ?? 0;
      if (pointRank !== selectedRank) return pointRank > selectedRank ? point : selected;
      return (point.metric_value ?? 0) >= (selected.metric_value ?? 0) ? point : selected;
    });
  });
}

// A compact bar-per-sample sparkline, colored by that sample's severity —
// real trend-history data (GET /api/instances/:name/trend/:category),
// not the design mock's synthetic series.
export default function WaitSparkline({
  instanceName,
  category = "wait_stats",
  hours = 24,
  height = 22,
}: {
  instanceName: string;
  category?: string;
  hours?: number;
  height?: number;
}) {
  const [points, setPoints] = useState<TrendPoint[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTrend(instanceName, category, hours)
      .then((res) => {
        if (!cancelled) setPoints(res.available ? res.points : []);
      })
      .catch(() => {
        if (!cancelled) setPoints([]);
      });
    return () => {
      cancelled = true;
    };
  }, [instanceName, category, hours]);

  if (!points || points.length === 0) {
    return <div style={{ height, flex: 1 }} />;
  }

  const visiblePoints = compactPoints(points);
  const max = Math.max(...visiblePoints.map((p) => p.metric_value ?? 0), 1);

  return (
    <div
      className="sparkline"
      style={{ height }}
      role="img"
      aria-label={`${category.replace(/_/g, " ")} trend over ${hours} hours`}
    >
      {visiblePoints.map((p, i) => (
        <div
          key={i}
          className="sparkline-bar"
          title={`${new Date(p.captured_at).toLocaleString()} — ${p.severity}`}
          style={{
            flex: 1,
            height: `${Math.max(8, ((p.metric_value ?? 0) / max) * 100)}%`,
            background: statusColorVar(p.severity),
            opacity: 0.35 + 0.65 * ((p.metric_value ?? 0) / max),
            borderRadius: 1.5,
          }}
        />
      ))}
    </div>
  );
}
