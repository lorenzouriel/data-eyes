import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import StatusBadge from "../components/StatusBadge";
import WaitSparkline from "../components/WaitSparkline";
import { getFleetHealth, getInstanceOverview } from "../api";
import type { FleetHealth, InstanceHealth, ServerOverview } from "../types";
import { statusColorVar, tagStyle } from "../strata";

const POLL_INTERVAL_MS = 30_000;

type Filter = "All" | "Critical" | "Warning" | "Healthy";
type Mode = "table" | "tiles";

function matchesFilter(instance: InstanceHealth, filter: Filter): boolean {
  if (filter === "All") return true;
  if (filter === "Critical") return instance.overall_severity === "CRITICAL";
  if (filter === "Warning") return instance.overall_severity === "WARNING";
  return instance.overall_severity === "OK" || instance.overall_severity === "UNKNOWN";
}

function alertCount(instance: InstanceHealth): number {
  return Object.values(instance.categories).filter((s) => s === "WARNING" || s === "CRITICAL").length;
}

function RowDetail({ instance }: { instance: InstanceHealth }) {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<ServerOverview | null | undefined>(undefined);

  useEffect(() => {
    getInstanceOverview(instance.name)
      .then((res) => setOverview(res.server.data))
      .catch(() => setOverview(null));
  }, [instance.name]);

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 26,
        alignItems: "flex-start",
        margin: "12px 0 4px 24px",
        padding: "14px 16px",
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 8,
      }}
    >
      {overview === undefined ? (
        <span style={{ color: "var(--muted)", fontSize: 12 }}>Loading server details…</span>
      ) : overview === null ? (
        <span style={{ color: "var(--muted)", fontSize: 12 }}>Server details unavailable — instance unreachable.</span>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 190 }}>
            <span className="th-label">ENGINE</span>
            <span className="mono" style={{ fontSize: 12 }}>
              {overview.ProductVersion ?? "—"} {overview.Edition ? `(${overview.Edition})` : ""}
            </span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>
              {overview.MachineName ?? "—"}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="th-label">MEMORY</span>
            <span className="mono" style={{ fontSize: 12 }}>{overview.TotalMemoryGB ? `${overview.TotalMemoryGB} GB` : "—"}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="th-label">DISK</span>
            <span className="mono" style={{ fontSize: 12 }}>{overview.TotalDiskGB ? `${overview.TotalDiskGB} GB` : "—"}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="th-label">CORES</span>
            <span className="mono" style={{ fontSize: 12 }}>{overview.Cores ?? "—"}</span>
          </div>
        </>
      )}
      <button className="btn-primary" style={{ marginLeft: "auto" }} onClick={() => navigate(`/instances/${encodeURIComponent(instance.name)}`)}>
        Open instance
      </button>
    </div>
  );
}

function FleetTable({ instances, expanded, onToggle }: { instances: InstanceHealth[]; expanded: string | null; onToggle: (name: string) => void }) {
  const navigate = useNavigate();
  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <div style={{ minWidth: 980, padding: "9px 16px", borderBottom: "1px solid var(--line)" }}>
        <div className="fleet-row-grid">
          <span />
          <span className="th-label">INSTANCE</span>
          <span className="th-label">STATUS</span>
          <span className="th-label">WAIT · 24H</span>
          <span className="th-label th-label--right">ALERTS</span>
          <span className="th-label">CATEGORIES</span>
          <span className="th-label th-label--right">DATABASES</span>
        </div>
      </div>
      {instances.map((instance) => {
        const isOpen = expanded === instance.name;
        const alerts = alertCount(instance);
        const waitPct = instance.metrics["wait_stats.Percentage_WaitTime"];
        return (
          <div key={instance.name}>
            <div
              onClick={() => onToggle(instance.name)}
              style={{
                cursor: "pointer",
                minWidth: 980,
                padding: "10px 16px",
                borderBottom: "1px solid var(--line2)",
                background: isOpen ? "var(--soft)" : "transparent",
              }}
            >
              <div className="fleet-row-grid">
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "var(--muted)", transform: `rotate(${isOpen ? 90 : 0}deg)`, transition: "transform .12s" }}>
                  ▶
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
                  <span className="status-dot" style={{ background: statusColorVar(instance.overall_severity) }} />
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/instances/${encodeURIComponent(instance.name)}`);
                      }}
                      style={{ font: "500 12.5px 'Space Grotesk', sans-serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    >
                      {instance.label}
                    </span>
                    <span className="mono" style={{ fontSize: 10, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {instance.environment ?? instance.name}
                    </span>
                  </div>
                </div>
                <span className="tag" style={{ justifySelf: "start", ...tagStyle(instance.reachable ? "var(--status-ok)" : "var(--muted)") }}>
                  {instance.reachable ? "ON" : "OFF"}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <WaitSparkline instanceName={instance.name} />
                  {waitPct !== undefined && (
                    <span className="mono" style={{ fontSize: 12.5, fontWeight: 500, flex: "none" }}>
                      {waitPct.toFixed(0)}%
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <span
                    className={alerts ? "tag" : ""}
                    style={alerts ? tagStyle(alerts > 2 ? "var(--status-crit)" : "var(--status-warn)") : { fontSize: 11, color: "var(--muted)" }}
                  >
                    {alerts ? alerts : "—"}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                  {Object.entries(instance.categories).map(([cat, sev]) => (
                    <span key={cat} className="status-dot" title={`${cat}: ${sev}`} style={{ background: statusColorVar(sev) }} />
                  ))}
                </div>
                <span className="mono" style={{ fontSize: 11.5, color: "var(--mid)", textAlign: "right" }}>
                  {instance.database_count ?? "—"}
                </span>
              </div>
            </div>
            {isOpen && <RowDetail instance={instance} />}
          </div>
        );
      })}
    </div>
  );
}

function FleetTiles({ instances }: { instances: InstanceHealth[] }) {
  const navigate = useNavigate();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(268px, 1fr))", gap: 12 }}>
      {instances.map((instance) => (
        <div
          key={instance.name}
          onClick={() => navigate(`/instances/${encodeURIComponent(instance.name)}`)}
          className="panel-card"
          style={{
            borderLeft: `3px solid ${statusColorVar(instance.overall_severity)}`,
            padding: "13px 15px",
            display: "flex",
            flexDirection: "column",
            gap: 11,
            cursor: "pointer",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span className="status-dot" style={{ background: statusColorVar(instance.overall_severity) }} />
            <span style={{ flex: 1, font: "500 13px 'Space Grotesk', sans-serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {instance.label}
            </span>
          </div>
          <WaitSparkline instanceName={instance.name} height={38} />
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
            <StatusBadge severity={instance.overall_severity} />
            <span className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>{instance.database_count ?? "—"} DBs</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function FleetStatus() {
  const [fleet, setFleet] = useState<FleetHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [mode, setMode] = useState<Mode>("table");
  const [filter, setFilter] = useState<Filter>("All");
  const [expanded, setExpanded] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getFleetHealth();
      setFleet(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load fleet health");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const instances = fleet?.instances ?? [];
  const counts: Record<Filter, number> = {
    All: instances.length,
    Critical: instances.filter((i) => i.overall_severity === "CRITICAL").length,
    Warning: instances.filter((i) => i.overall_severity === "WARNING").length,
    Healthy: instances.filter((i) => i.overall_severity === "OK" || i.overall_severity === "UNKNOWN").length,
  };
  const visible = instances.filter((i) => matchesFilter(i, filter));

  return (
    <AppShell active="status">
      <div className="page-inner">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">Status</h1>
            <p className="page-subtitle">
              {instances.length} monitored instance{instances.length === 1 ? "" : "s"}
              {lastUpdated && ` · updated ${lastUpdated.toLocaleTimeString()}`}
            </p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex" }}>
              {(["table", "tiles"] as Mode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  style={{
                    font: "500 11.5px 'Space Grotesk', sans-serif",
                    padding: "6px 12px",
                    border: `1px solid ${mode === m ? "var(--accent)" : "var(--line)"}`,
                    background: mode === m ? "var(--accentSoft)" : "var(--panel)",
                    color: mode === m ? "var(--accent)" : "var(--mid)",
                    cursor: "pointer",
                    borderRadius: m === "table" ? "7px 0 0 7px" : "0 7px 7px 0",
                  }}
                >
                  {m === "table" ? "Summary table" : "Tiles"}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {(["All", "Critical", "Warning", "Healthy"] as Filter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 7,
                    font: "500 11.5px 'Space Grotesk', sans-serif",
                    padding: "6px 11px",
                    borderRadius: 100,
                    cursor: "pointer",
                    border: `1px solid ${filter === f ? "var(--accent)" : "var(--line)"}`,
                    background: filter === f ? "var(--accentSoft)" : "var(--panel)",
                    color: filter === f ? "var(--accent)" : "var(--mid)",
                  }}
                >
                  {f !== "All" && (
                    <span
                      className="status-dot"
                      style={{ background: f === "Critical" ? "var(--status-crit)" : f === "Warning" ? "var(--status-warn)" : "var(--status-ok)" }}
                    />
                  )}
                  {f}
                  <span style={{ fontFamily: "JetBrains Mono, monospace", opacity: 0.65 }}>{counts[f]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <div className="banner-error">{error}</div>}
        {!fleet && !error && <div className="page-loading">Loading fleet…</div>}

        {fleet && visible.length === 0 && (
          <div className="empty-state">
            {instances.length === 0 ? (
              <>No instances registered yet — add one from the Admin panel.</>
            ) : (
              <>No instances match this filter.</>
            )}
          </div>
        )}

        {fleet && visible.length > 0 && mode === "table" && (
          <FleetTable instances={visible} expanded={expanded} onToggle={(name) => setExpanded(expanded === name ? null : name)} />
        )}
        {fleet && visible.length > 0 && mode === "tiles" && <FleetTiles instances={visible} />}
      </div>
    </AppShell>
  );
}
