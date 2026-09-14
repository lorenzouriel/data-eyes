import { useInstanceTab } from "../../hooks/useInstanceTab";
import { statusColorVar } from "../../strata";
import type { SessionDimensions, SessionRow } from "../../types";

function DimensionCard({ title, rows }: { title: string; rows: { Dimension: string; WaitSeconds: number }[] }) {
  const max = Math.max(...rows.map((r) => r.WaitSeconds), 1);
  return (
    <div className="panel-card" style={{ flex: "1 1 300px", minWidth: 280, overflow: "hidden" }}>
      <div style={{ padding: "13px 17px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ font: "500 13px 'Space Grotesk', sans-serif" }}>{title}</span>
        <span className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>wait, now</span>
      </div>
      {rows.length === 0 ? (
        <div className="table-empty">No active sessions right now.</div>
      ) : (
        rows.map((r, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: 7, padding: "11px 17px", borderBottom: "1px solid var(--line2)" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span className="mono" style={{ flex: 1, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.Dimension}</span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>{r.WaitSeconds.toFixed(1)}s</span>
            </div>
            <div style={{ height: 5, borderRadius: 3, background: "var(--soft)", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${(r.WaitSeconds / max) * 100}%`, background: "var(--accent)", borderRadius: 3 }} />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default function SessionsTab({ instanceName }: { instanceName: string }) {
  const { data, loading, error } = useInstanceTab(instanceName, "sessions");

  if (loading) return <div className="page-loading">Loading…</div>;
  if (error) return <div className="banner-error">{error}</div>;

  const dims = data?.dimensions?.data as unknown as SessionDimensions | null;
  const sessions = (data?.active_sessions?.data as unknown as SessionRow[] | null) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {data?.dimensions?.error ? (
        <div className="banner-error">{data.dimensions.error}</div>
      ) : dims ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          <DimensionCard title="Top users" rows={dims.users} />
          <DimensionCard title="Top programs" rows={dims.programs} />
          <DimensionCard title="Top hosts" rows={dims.hosts} />
        </div>
      ) : null}

      {data?.active_sessions?.error ? (
        <div className="banner-error">{data.active_sessions.error}</div>
      ) : (
        <div className="panel-card" style={{ overflowX: "auto" }}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", font: "500 13.5px 'Space Grotesk', sans-serif" }}>Active sessions</div>
          {sessions.length === 0 ? (
            <div className="table-empty">No active sessions right now.</div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "70px 1.4fr 130px 150px 82px 86px", padding: "9px 18px", borderBottom: "1px solid var(--line)" }}>
                <span className="th-label">PID</span>
                <span className="th-label">STATEMENT</span>
                <span className="th-label">USER</span>
                <span className="th-label">STATE</span>
                <span className="th-label th-label--right">WAIT</span>
                <span className="th-label th-label--right">ELAPSED</span>
              </div>
              {sessions.map((s) => (
                <div key={s.Pid} style={{ display: "grid", gridTemplateColumns: "70px 1.4fr 130px 150px 82px 86px", alignItems: "center", padding: "11px 18px", borderBottom: "1px solid var(--line2)" }}>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--mid)" }}>{s.Pid}</span>
                  <span className="mono" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: 18 }}>{s.SqlText || "—"}</span>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--mid)" }}>{s.LoginName}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span className="status-dot" style={{ background: s.WaitSeconds > 5 ? statusColorVar("CRITICAL") : s.WaitSeconds > 0 ? statusColorVar("WARNING") : statusColorVar("OK") }} />
                    <span style={{ fontSize: 11.5, color: "var(--mid)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.State}</span>
                  </div>
                  <span className="mono" style={{ fontSize: 12, textAlign: "right" }}>{s.WaitSeconds > 0 ? `${s.WaitSeconds.toFixed(1)}s` : "—"}</span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--mid)", textAlign: "right" }}>{s.ElapsedSeconds.toFixed(1)}s</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
