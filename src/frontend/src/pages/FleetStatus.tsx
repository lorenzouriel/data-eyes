import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import InstanceCard from "../components/InstanceCard";
import StatusSummaryPanel from "../components/StatusSummaryPanel";
import WaitSparkline from "../components/WaitSparkline";
import { getFleetHealth } from "../api";
import type { FleetHealth, InstanceHealth } from "../types";
import { DIAGNOSTIC_CATEGORY_ABBR, DIAGNOSTIC_CATEGORY_LABEL, DIAGNOSTIC_CATEGORY_ORDER, statusColorVar, tagStyle } from "../strata";

const POLL_INTERVAL_MS = 30_000;
const FLEET_ROW_MIN_WIDTH = 1120;

type Filter = "All" | "Critical" | "Warning" | "Healthy" | "Unknown";
type Mode = "table" | "cards";

interface EnvironmentGroup {
  environment: string;
  instances: InstanceHealth[];
}

function matchesFilter(instance: InstanceHealth, filter: Filter): boolean {
  if (filter === "All") return true;
  if (filter === "Critical") return instance.overall_severity === "CRITICAL";
  if (filter === "Warning") return instance.overall_severity === "WARNING";
  if (filter === "Unknown") return !instance.reachable || instance.overall_severity === "UNKNOWN";
  return instance.reachable && instance.overall_severity === "OK";
}

function alertCount(instance: InstanceHealth): number {
  return Object.values(instance.categories).filter((s) => s === "WARNING" || s === "CRITICAL").length;
}

// "MS SQL 2022 Developer"-style short label from server_overview's raw
// Edition string ("Developer Edition (64-bit)") — trims the parenthetical
// bitness suffix and the redundant trailing "Edition" word DPA's own Type
// column omits too.
function serverTypeLabel(instance: InstanceHealth): string {
  const edition = instance.server?.Edition;
  if (!edition) return "—";
  return edition.replace(/\s*\(.*\)\s*$/, "").replace(/\s*Edition\s*$/i, "").trim();
}

// Groups instances by their free-text `environment` field (from
// instances.yaml — no fixed enum), alphabetical, with anything missing or
// blank collected into a trailing "Ungrouped" bucket.
function groupByEnvironment(instances: InstanceHealth[]): EnvironmentGroup[] {
  const groups = new Map<string, InstanceHealth[]>();
  for (const instance of instances) {
    const key = instance.environment?.trim() || "Ungrouped";
    const list = groups.get(key) ?? [];
    list.push(instance);
    groups.set(key, list);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === "Ungrouped" ? 1 : b === "Ungrouped" ? -1 : a.localeCompare(b)))
    .map(([environment, list]) => ({ environment, instances: list }));
}

function CategoryIconRow({ instance, size = "grid" }: { instance: InstanceHealth; size?: "grid" | "inline" }) {
  const style = size === "grid"
    ? { display: "grid", gridTemplateColumns: "repeat(8, 1fr)", gap: 4 }
    : { display: "flex", gap: 5, flexWrap: "wrap" as const };
  return (
    <div style={style}>
      {DIAGNOSTIC_CATEGORY_ORDER.map((cat) => {
        const sev = instance.categories[cat];
        return (
          <span
            key={cat}
            className="status-dot"
            style={{ justifySelf: "center", background: sev ? statusColorVar(sev) : "var(--line2)" }}
            title={`${DIAGNOSTIC_CATEGORY_LABEL[cat]}: ${sev ?? "no data"}`}
          />
        );
      })}
    </div>
  );
}

function GroupHeader({ environment, count, collapsed, onToggle }: { environment: string; count: number; collapsed: boolean; onToggle: () => void }) {
  return (
    <div className="fleet-group-header" onClick={onToggle} style={{ minWidth: FLEET_ROW_MIN_WIDTH }}>
      <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>{collapsed ? "▸" : "▾"}</span>
      <span style={{ font: "500 12px 'Space Grotesk', sans-serif" }}>{environment}</span>
      <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>({count})</span>
    </div>
  );
}

function ReplicaSummary({ instance }: { instance: InstanceHealth }) {
  if (!instance.reachable || !instance.database_status) {
    return <span style={{ fontSize: 10, color: "var(--muted)" }}>Replica / access: unavailable</span>;
  }
  const databases = instance.database_status.filter(db => db.in_availability_group || db.updateability === "READ_ONLY");
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
      {databases.length === 0 ? <span style={{ fontSize: 10, color: "var(--muted)" }}>No Always On databases</span> : databases.map(db => (
        <span key={db.name} className="tag" style={{ whiteSpace: "normal", ...tagStyle("var(--accent)") }}
          title={`Database: ${db.name}; availability group: ${db.availability_group ?? (db.in_availability_group ? "Unknown" : "None")}`}>
          {db.name} · {db.in_availability_group ? `${db.replica_role ?? "ROLE UNKNOWN"} · ` : ""}
          {db.updateability === "READ_ONLY" ? "Read only" : db.updateability === "READ_WRITE" ? "Read/write" : "Access unknown"}
        </span>
      ))}
    </div>
  );
}

function FleetSummary({ instances }: { instances: InstanceHealth[] }) {
  return <StatusSummaryPanel variant="fleet" instances={instances} />;
}

function FleetTable({
  groups,
  collapsed,
  onToggleGroup,
  onSelect,
}: {
  groups: EnvironmentGroup[];
  collapsed: Set<string>;
  onToggleGroup: (env: string) => void;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <div style={{ minWidth: FLEET_ROW_MIN_WIDTH, padding: "9px 16px", borderBottom: "1px solid var(--line)" }}>
        <div className="fleet-row-grid">
          <span />
          <span className="th-label">INSTANCE</span>
          <span className="th-label">STATUS</span>
          <span className="th-label">WAIT · 24H</span>
          <span className="th-label th-label--right">ALERTS</span>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 1fr)", gap: 4 }}>
            {DIAGNOSTIC_CATEGORY_ORDER.map((cat) => (
              <span key={cat} className="th-label" style={{ textAlign: "center" }} title={DIAGNOSTIC_CATEGORY_LABEL[cat]}>
                {DIAGNOSTIC_CATEGORY_ABBR[cat]}
              </span>
            ))}
          </div>
          <span className="th-label th-label--right">DATABASES</span>
          <span className="th-label">TYPE</span>
        </div>
      </div>
      {groups.map((group) => (
        <div key={group.environment}>
          <GroupHeader
            environment={group.environment}
            count={group.instances.length}
            collapsed={collapsed.has(group.environment)}
            onToggle={() => onToggleGroup(group.environment)}
          />
          {!collapsed.has(group.environment) && group.instances.map((instance) => {
            const alerts = alertCount(instance);
            const waitPct = instance.metrics["wait_stats.Percentage_WaitTime"];
            return (
              <div key={instance.name}>
                <div
                  onClick={() => onSelect(instance.name)}
                  style={{
                    cursor: "pointer",
                    minWidth: FLEET_ROW_MIN_WIDTH,
                    padding: "10px 16px",
                    borderBottom: "1px solid var(--line2)",
                    background: "transparent",
                  }}
                >
                  <div className="fleet-row-grid">
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "var(--muted)" }}>
                      ›
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
                      <span className="status-dot" style={{ background: statusColorVar(instance.overall_severity) }} />
                      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                        <span
                          onClick={(e) => { e.stopPropagation(); onSelect(instance.name); }}
                          style={{ font: "500 12.5px 'Space Grotesk', sans-serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        >
                          {instance.label}
                        </span>
                        <span className="mono" style={{ fontSize: 10, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {instance.environment ?? instance.name}
                        </span>
                        <ReplicaSummary instance={instance} />
                      </div>
                    </div>
                    <span className="tag" style={{ justifySelf: "start", ...tagStyle(instance.reachable ? "var(--status-ok)" : "var(--muted)") }}>
                      {instance.reachable ? "ON" : "OFF"}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0, overflow: "hidden" }}>
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
                    <CategoryIconRow instance={instance} size="grid" />
                    <span className="mono" style={{ fontSize: 11.5, color: "var(--mid)", textAlign: "right" }}>
                      {instance.database_count ?? "—"}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--mid)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {serverTypeLabel(instance)}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function FleetCards({
  groups,
  collapsed,
  onToggleGroup,
  onSelect,
}: {
  groups: EnvironmentGroup[];
  collapsed: Set<string>;
  onToggleGroup: (env: string) => void;
  onSelect: (name: string) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {groups.map((group) => (
        <div key={group.environment} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div
            onClick={() => onToggleGroup(group.environment)}
            style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
          >
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>{collapsed.has(group.environment) ? "▸" : "▾"}</span>
            <span style={{ font: "500 12.5px 'Space Grotesk', sans-serif" }}>{group.environment}</span>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>({group.instances.length})</span>
          </div>
          {!collapsed.has(group.environment) && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))", gap: 12 }}>
              {group.instances.map((instance) => (
                <InstanceCard key={instance.name} instance={instance} onSelect={onSelect} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function FleetStatus() {
  const navigate = useNavigate();
  const [fleet, setFleet] = useState<FleetHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [mode, setMode] = useState<Mode>("table");
  const [filter, setFilter] = useState<Filter>("All");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

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
    Healthy: instances.filter((i) => i.reachable && i.overall_severity === "OK").length,
    Unknown: instances.filter((i) => !i.reachable || i.overall_severity === "UNKNOWN").length,
  };
  const visible = instances.filter((i) => matchesFilter(i, filter));
  const groups = groupByEnvironment(visible);

  const selectInstance = (name: string) => {
    navigate(`/instances/${encodeURIComponent(name)}`);
  };

  const toggleGroup = (env: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(env)) next.delete(env); else next.add(env);
      return next;
    });
  };

  return (
    <AppShell active="status">
      <div id="dashboard-top" className="page-inner">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">Fleet dashboard</h1>
            <p className="page-subtitle">
              {instances.length} monitored instance{instances.length === 1 ? "" : "s"}
              {lastUpdated && ` · updated ${lastUpdated.toLocaleTimeString()}`}
            </p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex" }}>
              {(["table", "cards"] as Mode[]).map((m) => (
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
                  {m === "table" ? "Summary table" : "Cards"}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {(["All", "Critical", "Warning", "Healthy", "Unknown"] as Filter[]).map((f) => (
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
                      style={{ background: f === "Critical" ? "var(--status-crit)" : f === "Warning" ? "var(--status-warn)" : f === "Unknown" ? "var(--muted)" : "var(--status-ok)" }}
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

        {fleet && instances.length > 0 && <FleetSummary instances={instances} />}

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
          <FleetTable
            groups={groups}
            collapsed={collapsed}
            onToggleGroup={toggleGroup}
            onSelect={selectInstance}
          />
        )}
        {fleet && visible.length > 0 && mode === "cards" && (
          <FleetCards groups={groups} collapsed={collapsed} onToggleGroup={toggleGroup} onSelect={selectInstance} />
        )}
      </div>
    </AppShell>
  );
}
