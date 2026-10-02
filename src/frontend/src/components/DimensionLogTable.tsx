import type { ActivityDimension, DimensionLogRow } from "../types";

const ACTIVITY_DIMENSIONS = new Set<ActivityDimension>([
  "waits",
  "programs",
  "databases",
  "machines",
  "db_users",
  "plans",
  "sql_statements",
]);

function fmtMs(v?: number | null): string {
  return v === null || v === undefined ? "—" : `${(v / 1000).toFixed(1)}s`;
}

function fmtNum(v?: number | null): string {
  return v === null || v === undefined ? "—" : `${v}`;
}

function fmtTime(iso?: string): string {
  return iso ? new Date(iso).toLocaleTimeString() : "—";
}

const CELL = { fontSize: 11.5, overflow: "hidden" as const, textOverflow: "ellipsis" as const, whiteSpace: "nowrap" as const };
const HEADER_ROW = { padding: "9px 18px", borderBottom: "1px solid var(--line)" };
const BODY_ROW = { alignItems: "center", padding: "9px 18px", borderBottom: "1px solid var(--line2)" };

// Raw-row drill-down for the Specific-Day range filter — column set adapts
// to whichever table app/repository.py's get_dimension_log() read from for
// this dimension (see DimensionLogRow's own comment in types.ts).
export default function DimensionLogTable({ dimension, rows }: { dimension: ActivityDimension; rows: DimensionLogRow[] }) {
  if (rows.length === 0) {
    return <div className="table-empty">No activity captured for this day yet.</div>;
  }

  if (ACTIVITY_DIMENSIONS.has(dimension)) {
    const cols = "96px 120px 140px 120px 120px 100px 70px 80px 1.6fr";
    return (
      <div className="panel-card" style={{ overflowX: "auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, ...HEADER_ROW }}>
          <span className="th-label">TIME</span>
          <span className="th-label">DATABASE</span>
          <span className="th-label">PROGRAM</span>
          <span className="th-label">HOST</span>
          <span className="th-label">USER</span>
          <span className="th-label">WAIT TYPE</span>
          <span className="th-label th-label--right">WAIT</span>
          <span className="th-label th-label--right">ELAPSED</span>
          <span className="th-label">SQL</span>
        </div>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: cols, ...BODY_ROW }}>
            <span className="mono" style={{ fontSize: 11 }}>{fmtTime(r.captured_at)}</span>
            <span style={CELL}>{r.database_name ?? "—"}</span>
            <span style={CELL}>{r.program_name ?? "—"}</span>
            <span style={CELL}>{r.host_name ?? "—"}</span>
            <span style={CELL}>{r.login_name ?? "—"}</span>
            <span style={{ ...CELL, color: "var(--mid)" }}>{r.wait_type ?? "—"}</span>
            <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>{fmtMs(r.wait_time_ms)}</span>
            <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>{fmtMs(r.elapsed_time_ms)}</span>
            <span className="mono" style={{ ...CELL, fontSize: 11 }}>{r.sql_text ?? "—"}</span>
          </div>
        ))}
      </div>
    );
  }

  if (dimension === "files" || dimension === "drives") {
    const cols = "96px 160px 1fr 120px 100px";
    return (
      <div className="panel-card" style={{ overflowX: "auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, ...HEADER_ROW }}>
          <span className="th-label">TIME</span>
          <span className="th-label">DATABASE</span>
          <span className="th-label">FILE</span>
          <span className="th-label">DRIVE</span>
          <span className="th-label th-label--right">IO STALL</span>
        </div>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: cols, ...BODY_ROW }}>
            <span className="mono" style={{ fontSize: 11 }}>{fmtTime(r.captured_at)}</span>
            <span style={CELL}>{r.database_name ?? "—"}</span>
            <span className="mono" style={{ ...CELL, fontSize: 11 }}>{r.file_name ?? "—"}</span>
            <span style={{ ...CELL, color: "var(--mid)" }}>{r.drive ?? "—"}</span>
            <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>{fmtMs(r.io_stall_ms)}</span>
          </div>
        ))}
      </div>
    );
  }

  if (dimension === "blocking_statements") {
    const cols = "96px 1.6fr 110px 90px 90px";
    return (
      <div className="panel-card" style={{ overflowX: "auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, ...HEADER_ROW }}>
          <span className="th-label">TIME</span>
          <span className="th-label">STATEMENT</span>
          <span className="th-label">LOCK</span>
          <span className="th-label th-label--right">BLOCKED</span>
          <span className="th-label th-label--right">DURATION</span>
        </div>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: cols, ...BODY_ROW }}>
            <span className="mono" style={{ fontSize: 11 }}>{fmtTime(r.captured_at)}</span>
            <span className="mono" style={{ ...CELL, fontSize: 11 }}>{r.root_sql ?? "—"}</span>
            <span style={{ ...CELL, color: "var(--mid)" }}>{r.lock_type ?? "—"}</span>
            <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>{fmtNum(r.blocked_count)}</span>
            <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>{r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : "—"}</span>
          </div>
        ))}
      </div>
    );
  }

  // deadlocks
  const cols = "96px 120px 130px 120px 130px 1fr 70px";
  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, ...HEADER_ROW }}>
        <span className="th-label">TIME</span>
        <span className="th-label">DATABASE</span>
        <span className="th-label">VICTIM LOGIN</span>
        <span className="th-label">VICTIM HOST</span>
        <span className="th-label">PROGRAM</span>
        <span className="th-label">RESOURCE</span>
        <span className="th-label th-label--right">PROCS</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: cols, ...BODY_ROW }}>
          <span className="mono" style={{ fontSize: 11 }}>{fmtTime(r.occurred_at)}</span>
          <span style={CELL}>{r.database_name ?? "—"}</span>
          <span style={CELL}>{r.victim_login ?? "—"}</span>
          <span style={CELL}>{r.victim_host ?? "—"}</span>
          <span style={CELL}>{r.victim_program ?? "—"}</span>
          <span style={{ ...CELL, color: "var(--mid)" }}>{r.resource_description ?? "—"}</span>
          <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>{fmtNum(r.process_count)}</span>
        </div>
      ))}
    </div>
  );
}
