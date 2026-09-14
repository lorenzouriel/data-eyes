import { useEffect, useState } from "react";
import { getTrend } from "../api";
import { statusColorVar } from "../strata";
import type { TrendPoint } from "../types";

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

  const max = Math.max(...points.map((p) => p.metric_value ?? 0), 1);

  return (
    <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 1.5, height }}>
      {points.map((p, i) => (
        <div
          key={i}
          title={`${new Date(p.captured_at).toLocaleString()} — ${p.severity}`}
          style={{
            flex: 1,
            minWidth: 2,
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
