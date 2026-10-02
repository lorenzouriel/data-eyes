import { colorForCategory, labelForCategory } from "../../strata";

export interface HourStackPoint {
  captured_at: string;
  category: string;
  value: number;
}

export type ChartGranularity = "hour" | "day";

// Hour buckets derive their key from Date getters (local time) since
// captured_at is a full timestamp; day buckets use the date string itself
// (already day-granular, coming pre-bucketed from the server's Top-N
// endpoints) to sidestep UTC/local-timezone date-shifting entirely.
export function bucketByPeriod(
  points: HourStackPoint[],
  granularity: ChartGranularity = "hour",
): { periodLabel: string; byCategory: Record<string, number> }[] {
  const buckets = new Map<string, { sortKey: string; label: string; byCategory: Record<string, number> }>();
  for (const p of points) {
    let sortKey: string;
    let label: string;
    if (granularity === "day") {
      sortKey = p.captured_at.slice(0, 10);
      label = new Date(`${sortKey}T00:00:00Z`).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      });
    } else {
      const d = new Date(p.captured_at);
      sortKey = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}-${String(d.getHours()).padStart(2, "0")}`;
      label = `${String(d.getHours()).padStart(2, "0")}:00`;
    }
    const existing = buckets.get(sortKey) ?? { sortKey, label, byCategory: {} };
    existing.byCategory[p.category] = (existing.byCategory[p.category] ?? 0) + p.value;
    buckets.set(sortKey, existing);
  }
  return Array.from(buckets.values())
    .sort((a, b) => (a.sortKey < b.sortKey ? -1 : 1))
    .map(({ label, byCategory }) => ({ periodLabel: label, byCategory }));
}

// Shared by WaitsTab (wait time by category, hourly), BlockingTab (blocking
// impact by lock type, hourly), and TopActivityTab (every Top-N dimension,
// daily) — all need the identical bucket-by-period stacked bar + side
// legend, differing only in what {captured_at, category, value} is adapted
// from and whether the period is an hour or a day.
export default function StackedHourChart({
  points,
  emptyMessage,
  granularity = "hour",
}: {
  points: HourStackPoint[];
  emptyMessage: string;
  granularity?: ChartGranularity;
}) {
  if (points.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "24px 0" }}>
        {emptyMessage}
      </div>
    );
  }
  const hours = bucketByPeriod(points, granularity);
  const totals = hours.map((h) => Object.values(h.byCategory).reduce((a, b) => a + b, 0));
  const max = Math.max(...totals, 1);

  const legendTotals: Record<string, number> = {};
  for (const p of points) legendTotals[p.category] = (legendTotals[p.category] ?? 0) + p.value;
  const grandTotal = Object.values(legendTotals).reduce((a, b) => a + b, 0) || 1;

  // Whatever categories actually show up in this data, biggest contributor
  // first — no fixed enum, so a category that isn't one of the known coarse
  // buckets still gets its own series instead of vanishing into a catch-all.
  const categoriesBySize = Object.keys(legendTotals).sort((a, b) => legendTotals[b] - legendTotals[a]);

  return (
    <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 210 }}>
          {hours.map((h, i) => (
            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column-reverse", gap: 1.5, height: "100%" }} title={h.periodLabel}>
              {categoriesBySize.filter((c) => h.byCategory[c]).map((c) => (
                <div
                  key={c}
                  style={{
                    height: `${((h.byCategory[c] ?? 0) / max) * 100}%`,
                    background: colorForCategory(c),
                    borderRadius: h.byCategory[c] === Math.max(...Object.values(h.byCategory)) ? "2px 2px 0 0" : 0,
                  }}
                />
              ))}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
          <span>{hours[0]?.periodLabel}</span>
          <span>{hours[hours.length - 1]?.periodLabel}</span>
        </div>
      </div>
      <div style={{ flex: "none", width: 168, display: "flex", flexDirection: "column", gap: 2, paddingLeft: 18, borderLeft: "1px solid var(--line)" }}>
        {categoriesBySize.map((c) => (
          <div key={c} style={{ display: "flex", alignItems: "center", gap: 9, padding: "5px 0" }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: colorForCategory(c), flex: "none" }} />
            <span style={{ flex: 1, fontSize: 11.5, color: "var(--mid)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {labelForCategory(c)}
            </span>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {Math.round((100 * legendTotals[c]) / grandTotal)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
