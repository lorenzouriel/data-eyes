import { useEffect, useState } from "react";
import { getDimensionLog, getTopDimension } from "../../api";
import type { ActivityDimension, DimensionLogRow, TopDimensionResponse } from "../../types";
import StackedHourChart, { type HourStackPoint } from "../charts/StackedHourChart";
import DimensionLogTable from "../DimensionLogTable";
import RangeFilter, { todayIso, type RangeValue } from "../RangeFilter";

const DIMENSIONS: { key: ActivityDimension; label: string }[] = [
  { key: "waits", label: "Waits" },
  { key: "programs", label: "Programs" },
  { key: "databases", label: "Databases" },
  { key: "machines", label: "Machines" },
  { key: "db_users", label: "DB Users" },
  { key: "files", label: "Files" },
  { key: "drives", label: "Drives" },
  { key: "plans", label: "Plans" },
  { key: "sql_statements", label: "SQL Statements" },
  { key: "blocking_statements", label: "Blocking Statements" },
  { key: "deadlocks", label: "Deadlocks" },
];

const ACTIVITY_SAMPLE_DIMENSIONS = new Set<ActivityDimension>([
  "waits",
  "programs",
  "databases",
  "machines",
  "db_users",
  "plans",
  "sql_statements",
]);

// Adapts one day's raw drill-down rows (DimensionLogRow, whatever table
// get_dimension_log read from — see types.ts) into {captured_at, category,
// value} points for the shared hourly StackedHourChart, picking whichever
// category/value field is meaningful for this dimension.
function logRowsToHourPoints(dimension: ActivityDimension, rows: DimensionLogRow[]): HourStackPoint[] {
  if (ACTIVITY_SAMPLE_DIMENSIONS.has(dimension)) {
    const categoryOf: Record<string, (r: DimensionLogRow) => string> = {
      waits: (r) => r.wait_category || r.wait_type || "idle",
      programs: (r) => r.program_name || "unknown",
      databases: (r) => r.database_name || "unknown",
      machines: (r) => r.host_name || "unknown",
      db_users: (r) => r.login_name || "unknown",
      plans: (r) => r.plan_handle || "unknown",
      sql_statements: (r) => (r.sql_text ? r.sql_text.slice(0, 40) : "unknown"),
    };
    const pick = categoryOf[dimension];
    return rows.map((r) => ({
      captured_at: r.captured_at ?? "",
      category: pick(r),
      value: (r.wait_time_ms ?? 0) / 1000,
    }));
  }
  if (dimension === "files" || dimension === "drives") {
    return rows.map((r) => ({
      captured_at: r.captured_at ?? "",
      category: (dimension === "files" ? r.file_name : r.drive) || "unknown",
      value: (r.io_stall_ms ?? 0) / 1000,
    }));
  }
  if (dimension === "blocking_statements") {
    return rows.map((r) => ({
      captured_at: r.captured_at ?? "",
      category: r.lock_type || "unknown",
      value: r.duration_seconds ?? 0,
    }));
  }
  // deadlocks
  return rows.map((r) => ({ captured_at: r.occurred_at ?? "", category: "deadlocks", value: 1 }));
}

export default function TopActivityTab({ instanceName }: { instanceName: string }) {
  const [dimension, setDimension] = useState<ActivityDimension>("waits");
  const [range, setRange] = useState<RangeValue>({ mode: "30d", day: todayIso() });

  const [chart, setChart] = useState<TopDimensionResponse | null>(null);
  const [logRows, setLogRows] = useState<DimensionLogRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setChart(null);
    setLogRows(null);

    if (range.mode === "day") {
      getDimensionLog(instanceName, dimension, range.day)
        .then((res) => {
          if (cancelled) return;
          setLogRows(res.rows);
          setLoading(false);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Failed to load the activity log");
          setLoading(false);
        });
    } else {
      getTopDimension(instanceName, dimension, range.mode)
        .then((res) => {
          if (cancelled) return;
          setChart(res);
          setLoading(false);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Failed to load activity history");
          setLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
    // Only re-fetch on day changes while in day mode.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instanceName, dimension, range.mode, range.mode === "day" ? range.day : null]);

  const chartPoints: HourStackPoint[] = chart
    ? [
        ...chart.series.flatMap((s) => s.points.map((p) => ({ captured_at: p.day, category: s.label, value: p.value }))),
        ...chart.other.map((p) => ({ captured_at: p.day, category: "Other", value: p.value })),
      ]
    : [];

  const activeLabel = DIMENSIONS.find((d) => d.key === dimension)?.label ?? dimension;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {DIMENSIONS.map((d) => (
          <button
            key={d.key}
            onClick={() => setDimension(d.key)}
            style={{
              font: "500 11.5px 'Space Grotesk', sans-serif",
              padding: "6px 11px",
              borderRadius: 100,
              cursor: "pointer",
              border: `1px solid ${dimension === d.key ? "var(--accent)" : "var(--line)"}`,
              background: dimension === d.key ? "var(--accentSoft)" : "var(--panel)",
              color: dimension === d.key ? "var(--accent)" : "var(--mid)",
            }}
          >
            {d.label}
          </button>
        ))}
      </div>

      <RangeFilter value={range} onChange={setRange} />

      {loading && <div className="page-loading">Loading…</div>}
      {error && <div className="banner-error">{error}</div>}

      {!loading && !error && range.mode !== "day" && chart && (
        <div className="panel-card" style={{ padding: "18px 20px 14px", display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ font: "500 13.5px 'Space Grotesk', sans-serif" }}>
              Top {activeLabel} by {dimension === "deadlocks" ? "count" : "wait time"}
            </span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>
              {range.mode === "7d" ? "last 7 days" : "last 30 days"}
            </span>
          </div>
          <StackedHourChart
            points={chartPoints}
            granularity="day"
            emptyMessage="No history yet for this range — this fills in as the collector runs."
          />
        </div>
      )}

      {!loading && !error && range.mode === "day" && logRows && (
        <>
          <div className="panel-card" style={{ padding: "18px 20px 14px", display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ font: "500 13.5px 'Space Grotesk', sans-serif" }}>
                {activeLabel} by hour — {range.day}
              </span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>
                {dimension === "deadlocks" ? "count" : dimension === "blocking_statements" || dimension === "files" || dimension === "drives" ? "seconds" : "seconds of wait"}
              </span>
            </div>
            <StackedHourChart
              points={logRowsToHourPoints(dimension, logRows)}
              granularity="hour"
              emptyMessage="No activity captured on this day."
            />
          </div>
          <DimensionLogTable dimension={dimension} rows={logRows} />
        </>
      )}
    </div>
  );
}
