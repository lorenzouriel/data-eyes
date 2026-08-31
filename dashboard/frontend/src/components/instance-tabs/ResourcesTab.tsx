import { useInstanceTab } from "../../hooks/useInstanceTab";
import WaitSparkline from "../WaitSparkline";
import type { AGHealthRow, ResourceUtilization } from "../../types";

function CpuCard({ history }: { history: { TimestampMs: number; CpuPct: number }[] }) {
  const points = history.filter((p) => p.CpuPct !== null && p.CpuPct !== undefined);
  const latest = points[points.length - 1]?.CpuPct;
  const max = Math.max(...points.map((p) => p.CpuPct), 1);
  return (
    <div className="panel-card" style={{ padding: "16px 17px", display: "flex", flexDirection: "column", gap: 12 }}>
      <span className="th-label">CPU UTILIZATION</span>
      <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
        <span style={{ font: "600 25px 'Space Grotesk', sans-serif", letterSpacing: "-.8px" }}>{latest ?? "—"}</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>%</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 34 }}>
        {points.map((p, i) => (
          <div key={i} style={{ flex: 1, height: `${Math.max(8, (p.CpuPct / max) * 100)}%`, background: "var(--accent)", opacity: 0.4 + 0.6 * (p.CpuPct / max), borderRadius: 1.5 }} />
        ))}
      </div>
      <span style={{ fontSize: 11, color: "var(--muted)" }}>from SQL Server's own scheduler-monitor ring buffer, ~1min samples</span>
    </div>
  );
}

function GaugeCard({ label, value, unit, note }: { label: string; value: number | string | null; unit: string; note: string }) {
  return (
    <div className="panel-card" style={{ padding: "16px 17px", display: "flex", flexDirection: "column", gap: 12 }}>
      <span className="th-label">{label}</span>
      <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
        <span style={{ font: "600 25px 'Space Grotesk', sans-serif", letterSpacing: "-.8px" }}>{value ?? "—"}</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>{unit}</span>
      </div>
      <span style={{ fontSize: 11, color: "var(--muted)" }}>{note}</span>
    </div>
  );
}

function RateCard({ instanceName, category, label, unit }: { instanceName: string; category: string; label: string; unit: string }) {
  return (
    <div className="panel-card" style={{ padding: "16px 17px", display: "flex", flexDirection: "column", gap: 12 }}>
      <span className="th-label">{label}</span>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 34 }}>
        <WaitSparkline instanceName={instanceName} category={category} height={34} />
      </div>
      <span style={{ fontSize: 11, color: "var(--muted)" }}>{unit} · collected every cycle, fills in over time</span>
    </div>
  );
}

export default function ResourcesTab({ instanceName }: { instanceName: string }) {
  const { data, loading, error } = useInstanceTab(instanceName, "resources");

  if (loading) return <div className="page-loading">Loading…</div>;
  if (error) return <div className="banner-error">{error}</div>;

  if (data?.resources?.error) return <div className="banner-error">{data.resources.error}</div>;
  const res = data?.resources?.data as unknown as ResourceUtilization | null;
  const ag = (data?.ag_health?.data as unknown as AGHealthRow[] | null) ?? [];

  if (!res) return <div className="table-empty">No resource data available.</div>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 14 }}>
      <CpuCard history={res.cpu_history} />
      <GaugeCard label="BUFFER CACHE HIT" value={res.buffer_cache_hit_pct} unit="%" note="share of page requests served from memory" />
      <GaugeCard
        label="PAGE LIFE EXPECTANCY"
        value={res.page_life_expectancy_seconds}
        unit="s"
        note={res.page_life_expectancy_seconds && res.page_life_expectancy_seconds < 300 ? "below the 300s comfort threshold" : "comfortably above the 300s threshold"}
      />
      <RateCard instanceName={instanceName} category="disk_io" label="DISK READ" unit="MB/s" />
      <RateCard instanceName={instanceName} category="batch_requests" label="BATCH REQUESTS" unit="req/s" />
      {ag.length > 0 && (
        <GaugeCard label="AG REDO QUEUE" value={ag[0]?.RedoQueueKB ?? null} unit="KB" note={ag[0]?.SyncHealth ?? ""} />
      )}
    </div>
  );
}
