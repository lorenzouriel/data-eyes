import { useInstanceTab } from "../../hooks/useInstanceTab";
import { statusColorVar, tagStyle } from "../../strata";
import type { BlockingEvent, BlockingRow } from "../../types";

function depthOf(row: BlockingRow, byBlockedId: Map<number, BlockingRow>, seen = new Set<number>()): number {
  if (seen.has(row.BlockedSessionID)) return 0; // guard against a malformed cycle
  seen.add(row.BlockedSessionID);
  const parent = byBlockedId.get(row.BlockingSessionID);
  return parent ? 1 + depthOf(parent, byBlockedId, seen) : 0;
}

function BlockingChain({ rows }: { rows: BlockingRow[] }) {
  if (rows.length === 0) {
    return <div className="empty-state" style={{ padding: "24px 0" }}>No active blocking right now.</div>;
  }
  const byBlockedId = new Map(rows.map((r) => [r.BlockedSessionID, r]));
  const sorted = [...rows].sort((a, b) => depthOf(a, byBlockedId) - depthOf(b, byBlockedId));

  return (
    <div className="panel-card" style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <span style={{ font: "500 13.5px 'Space Grotesk', sans-serif" }}>Active blocking</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
          {rows.length} session{rows.length === 1 ? "" : "s"} waiting
        </span>
      </div>
      {sorted.map((r, i) => {
        const depth = depthOf(r, byBlockedId);
        const root = depth === 0;
        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 11,
              padding: "12px 14px",
              borderRadius: 8,
              border: `1px solid ${root ? "var(--status-crit)" : "var(--line)"}`,
              background: root ? "var(--soft)" : "transparent",
            }}
          >
            <span style={{ flex: "none", width: depth * 22 }} />
            <span className="status-dot" style={{ background: root ? "var(--status-crit)" : "var(--status-warn)" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0, flex: 1 }}>
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 9 }}>
                <span className="mono" style={{ fontSize: 12.5, fontWeight: 500 }}>spid {r.BlockedSessionID}</span>
                <span className="tag" style={tagStyle(root ? "var(--status-crit)" : "var(--mid)")}>
                  {root ? "HEAD BLOCKER'S VICTIM" : `BLOCKED BY ${r.BlockingSessionID}`}
                </span>
                <span style={{ fontSize: 11.5, color: "var(--mid)" }}>{r.BlockedLoginName}</span>
              </div>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.BlockedQueryText}
              </span>
            </div>
            <div style={{ flex: "none", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
              <span className="mono" style={{ fontSize: 12.5, fontWeight: 500 }}>{r.WaitTimeSeconds.toFixed(1)}s</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>{r.WaitType}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BlockingEventsLog({ events }: { events: BlockingEvent[] }) {
  if (events.length === 0) {
    return <div className="table-empty">No blocking events logged in this window.</div>;
  }
  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", font: "500 13.5px 'Space Grotesk', sans-serif" }}>
        Blocking events, last 24 hours
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "96px 1.6fr 110px 90px 90px", padding: "9px 18px", borderBottom: "1px solid var(--line)" }}>
        <span className="th-label">TIME</span>
        <span className="th-label">STATEMENT</span>
        <span className="th-label">LOCK</span>
        <span className="th-label th-label--right">BLOCKED</span>
        <span className="th-label th-label--right">DURATION</span>
      </div>
      {events.map((e, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "96px 1.6fr 110px 90px 90px", alignItems: "center", padding: "11px 18px", borderBottom: "1px solid var(--line2)" }}>
          <span className="mono" style={{ fontSize: 11.5, color: "var(--mid)" }}>{new Date(e.captured_at).toLocaleTimeString()}</span>
          <span className="mono" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: 18 }}>
            {e.root_sql ?? "—"}
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--mid)" }}>{e.lock_type ?? "—"}</span>
          <span className="mono" style={{ fontSize: 12, textAlign: "right" }}>{e.blocked_count}</span>
          <span className="mono" style={{ fontSize: 12, textAlign: "right", color: e.duration_seconds >= 30 ? statusColorVar("CRITICAL") : "var(--mid)" }}>
            {e.duration_seconds.toFixed(1)}s
          </span>
        </div>
      ))}
    </div>
  );
}

export default function BlockingTab({ instanceName }: { instanceName: string }) {
  const { data, loading, error } = useInstanceTab(instanceName, "blocking");

  if (loading) return <div className="page-loading">Loading…</div>;
  if (error) return <div className="banner-error">{error}</div>;

  const blocking = (data?.blocking?.data as unknown as BlockingRow[] | null) ?? [];
  const events = (data?.blocking_events?.data as unknown as BlockingEvent[] | null) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {data?.blocking?.error ? <div className="banner-error">{data.blocking.error}</div> : <BlockingChain rows={blocking} />}
      {data?.blocking_events?.error ? <div className="banner-error">{data.blocking_events.error}</div> : <BlockingEventsLog events={events} />}
    </div>
  );
}
