import { useNavigate } from "react-router-dom";
import { statusColorVar } from "../../../shared/styles/strata";
import type { AlertDefinition, AlertEvent, AlertState } from "../types";
import { EmptyPanel, SeverityTag, bySeverity, formatValue, timeAgo } from "./shared";

const SELF_INSTANCE = "Data Eyes";

interface Props {
  states: AlertState[];
  events: AlertEvent[];
  byKey: Map<string, AlertDefinition>;
  instanceCount: number;
}

function Tile({ label, value, color, hint }: { label: string; value: number | string; color?: string; hint?: string }) {
  return <div className="status-tile" style={{ borderLeftColor: color ?? "var(--line)" }} title={hint}>
    <span className="status-tile-label">{label}</span>
    <span className="status-tile-value" style={{ fontSize: 20, color: color && value ? color : undefined }}>{value}</span>
  </div>;
}

export default function AlertsOverview({ states, events, byKey, instanceCount }: Props) {
  const navigate = useNavigate();
  const open = states.filter(s => s.severity === "WARNING" || s.severity === "CRITICAL" || s.severity === "UNKNOWN");
  const failing = states.filter(s => s.status === "error");
  const unreachable = new Set(states.filter(s => s.alert_key === "sql_server_connection" && s.severity === "CRITICAL").map(s => s.instance_name));
  const dayAgo = Date.now() - 24 * 3600 * 1000;
  const recentEvents = events.filter(e => new Date(e.captured_at).getTime() >= dayAgo).length;

  const instances = [...new Set(open.map(s => s.instance_name))]
    .map(name => ({ name, alerts: open.filter(s => s.instance_name === name).sort((a, b) => bySeverity(a.severity, b.severity)) }))
    .sort((a, b) => bySeverity(a.alerts[0].severity, b.alerts[0].severity) || b.alerts.length - a.alerts.length || a.name.localeCompare(b.name));

  return <div className="alerts-stack">
    <div className="status-tile-grid">
      <Tile label="Critical" value={open.filter(s => s.severity === "CRITICAL").length} color={statusColorVar("CRITICAL")} />
      <Tile label="Warning" value={open.filter(s => s.severity === "WARNING").length} color={statusColorVar("WARNING")} />
      <Tile label="Unreachable" value={`${unreachable.size} / ${instanceCount}`} color={unreachable.size ? statusColorVar("CRITICAL") : undefined}
        hint="Instances whose SQL Server Connection alert is critical" />
      <Tile label="Checks failing" value={failing.length} color={failing.length ? "var(--muted)" : undefined}
        hint="Checks that could not run, usually a missing permission" />
      <Tile label="Events · 24 h" value={recentEvents} />
    </div>

    {!instances.length && <EmptyPanel title="All clear">Every enabled check passed its last run.</EmptyPanel>}

    {instances.map(({ name, alerts }) => {
      const critical = alerts.filter(a => a.severity === "CRITICAL").length;
      return <section key={name} className="panel-card alerts-card">
        <header className="alerts-card-header">
          <div className="alerts-card-title">
            <span className="status-dot" style={{ background: statusColorVar(alerts[0].severity) }} />
            <strong>{name}</strong>
            <span className="alerts-muted">{critical ? `${critical} critical · ` : ""}{alerts.length - critical} other open</span>
          </div>
          {name !== SELF_INSTANCE && <button type="button" className="btn-ghost" onClick={() => navigate(`/instances/${encodeURIComponent(name)}`)}>Open instance</button>}
        </header>
        {alerts.map(s => {
          const definition = byKey.get(s.alert_key);
          const lines = s.detail ? s.detail.split("\n") : [];
          return <div key={s.alert_key} className="alerts-open-row">
            <SeverityTag severity={s.severity} />
            <div className="alerts-open-name">
              <span>{definition?.name ?? s.alert_key}</span>
              <span className="alerts-muted">{definition?.group}</span>
            </div>
            <span className="alerts-open-value">{formatValue(s.metric_value, definition?.unit)}</span>
            <div className="alerts-detail">
              {s.status === "error" && <span className="alerts-error">Check failed: {s.status_message}</span>}
              {lines.slice(0, 3).map((line, i) => <span key={i}>{line.replace(/^(CRITICAL|WARNING) /, "")}</span>)}
              {lines.length > 3 && <span className="alerts-muted">+{lines.length - 3} more</span>}
            </div>
            <span className="alerts-muted alerts-open-since" title={new Date(s.changed_at).toLocaleString()}>since {timeAgo(s.changed_at)}</span>
          </div>;
        })}
      </section>;
    })}

    {failing.length > 0 && <section className="panel-card alerts-card">
      <header className="alerts-card-header">
        <div className="alerts-card-title"><strong>Checks that could not run</strong>
          <span className="alerts-muted">Grant the permission listed on Settings, or turn the alert off.</span></div>
      </header>
      {failing.map(s => <div key={`${s.instance_name}/${s.alert_key}`} className="alerts-failing-row">
        <span>{s.instance_name}</span>
        <span>{byKey.get(s.alert_key)?.name ?? s.alert_key}</span>
        <span className="alerts-error">{s.status_message}</span>
        <span className="alerts-muted">{byKey.get(s.alert_key)?.permission}</span>
      </div>)}
    </section>}
  </div>;
}
