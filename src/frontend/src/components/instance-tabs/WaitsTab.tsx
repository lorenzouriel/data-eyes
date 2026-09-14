import { useInstanceTab } from "../../hooks/useInstanceTab";
import { CATEGORY_COLOR, CATEGORY_LABEL } from "../../strata";
import type { WaitCategoryPoint, WaitStatRow } from "../../types";

const CATEGORY_ORDER = ["cpu", "lock", "disk", "network", "other"];

function bucketByHour(points: WaitCategoryPoint[]): { hourLabel: string; byCategory: Record<string, number> }[] {
  const buckets = new Map<string, Record<string, number>>();
  for (const p of points) {
    const d = new Date(p.captured_at);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}-${d.getHours()}`;
    const existing = buckets.get(key) ?? {};
    existing[p.category] = (existing[p.category] ?? 0) + p.seconds;
    buckets.set(key, existing);
  }
  return Array.from(buckets.entries())
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([key, byCategory]) => {
      const hour = key.split("-")[3];
      return { hourLabel: `${hour.padStart(2, "0")}:00`, byCategory };
    });
}

function StackedChart({ points }: { points: WaitCategoryPoint[] }) {
  if (points.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "24px 0" }}>
        No wait-category history yet — this fills in over the next few collector cycles.
      </div>
    );
  }
  const hours = bucketByHour(points);
  const totals = hours.map((h) => Object.values(h.byCategory).reduce((a, b) => a + b, 0));
  const max = Math.max(...totals, 1);

  const legendTotals: Record<string, number> = {};
  for (const p of points) legendTotals[p.category] = (legendTotals[p.category] ?? 0) + p.seconds;
  const grandTotal = Object.values(legendTotals).reduce((a, b) => a + b, 0) || 1;

  return (
    <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 210 }}>
          {hours.map((h, i) => (
            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column-reverse", gap: 1.5, height: "100%" }} title={h.hourLabel}>
              {CATEGORY_ORDER.filter((c) => h.byCategory[c]).map((c) => (
                <div
                  key={c}
                  style={{
                    height: `${((h.byCategory[c] ?? 0) / max) * 100}%`,
                    background: CATEGORY_COLOR[c],
                    borderRadius: h.byCategory[c] === Math.max(...Object.values(h.byCategory)) ? "2px 2px 0 0" : 0,
                  }}
                />
              ))}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
          <span>{hours[0]?.hourLabel}</span>
          <span>{hours[hours.length - 1]?.hourLabel}</span>
        </div>
      </div>
      <div style={{ flex: "none", width: 168, display: "flex", flexDirection: "column", gap: 2, paddingLeft: 18, borderLeft: "1px solid var(--line)" }}>
        {CATEGORY_ORDER.filter((c) => legendTotals[c]).map((c) => (
          <div key={c} style={{ display: "flex", alignItems: "center", gap: 9, padding: "5px 0" }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: CATEGORY_COLOR[c], flex: "none" }} />
            <span style={{ flex: 1, fontSize: 11.5, color: "var(--mid)" }}>{CATEGORY_LABEL[c]}</span>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {Math.round((100 * legendTotals[c]) / grandTotal)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WaitTypesTable({ rows }: { rows: WaitStatRow[] }) {
  if (rows.length === 0) return <div className="table-empty">No significant wait statistics found.</div>;
  const max = Math.max(...rows.map((r) => r.Percentage_WaitTime), 1);
  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", font: "500 13.5px 'Space Grotesk', sans-serif" }}>Wait types</div>
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 84px 78px", padding: "9px 18px", borderBottom: "1px solid var(--line)" }}>
        <span className="th-label">WAIT TYPE</span>
        <span className="th-label">SHARE</span>
        <span className="th-label th-label--right">WAIT</span>
        <span className="th-label th-label--right">TASKS</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 84px 78px", alignItems: "center", padding: "11px 18px", borderBottom: "1px solid var(--line2)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: CATEGORY_COLOR[r.Category] ?? CATEGORY_COLOR.other, flex: "none" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
              <span className="mono" style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.Wait_Type}</span>
              <span style={{ fontSize: 10.5, color: "var(--muted)" }}>{CATEGORY_LABEL[r.Category] ?? r.Category}</span>
            </div>
          </div>
          <div style={{ paddingRight: 22 }}>
            <div style={{ height: 6, borderRadius: 3, background: "var(--soft)", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${(r.Percentage_WaitTime / max) * 100}%`, background: CATEGORY_COLOR[r.Category] ?? CATEGORY_COLOR.other, borderRadius: 3 }} />
            </div>
          </div>
          <span className="mono" style={{ fontSize: 12, textAlign: "right" }}>{r.Wait_Time_Seconds.toFixed(1)}s</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--mid)", textAlign: "right" }}>{r.Waiting_Tasks_Count}</span>
        </div>
      ))}
    </div>
  );
}

export default function WaitsTab({ instanceName }: { instanceName: string }) {
  const { data, loading, error } = useInstanceTab(instanceName, "waits");

  if (loading) return <div className="page-loading">Loading…</div>;
  if (error) return <div className="banner-error">{error}</div>;

  const waitStats = (data?.wait_stats?.data as unknown as WaitStatRow[] | null) ?? [];
  const waitStatsError = data?.wait_stats?.error;
  const history = (data?.wait_category_history?.data as unknown as WaitCategoryPoint[] | null) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="panel-card" style={{ padding: "18px 20px 14px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ font: "500 13.5px 'Space Grotesk', sans-serif" }}>Wait time by hour</span>
          <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>seconds of wait, by category</span>
        </div>
        <StackedChart points={history} />
      </div>

      {waitStatsError ? <div className="banner-error">{waitStatsError}</div> : <WaitTypesTable rows={waitStats} />}
    </div>
  );
}
