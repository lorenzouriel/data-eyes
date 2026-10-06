import { useMemo, useState } from "react";
import type { AlertDefinition, AlertEvent } from "../types";
import { EmptyPanel, SeverityTag, timeAgo } from "./shared";

interface Props {
  events: AlertEvent[];
  byKey: Map<string, AlertDefinition>;
}

export default function AlertEvents({ events, byKey }: Props) {
  const [instance, setInstance] = useState("");
  const [severity, setSeverity] = useState<"" | "CRITICAL" | "WARNING">("");
  const [search, setSearch] = useState("");
  const instances = useMemo(() => [...new Set(events.map(e => e.instance_name))].sort(), [events]);
  const shown = events.filter(e => (!instance || e.instance_name === instance) && (!severity || e.severity === severity)
    && (!search || `${byKey.get(e.alert_key)?.name ?? e.alert_key} ${e.detail}`.toLowerCase().includes(search.toLowerCase())));

  return <div className="alerts-stack">
    <div className="alerts-toolbar field">
      <label>Instance<select value={instance} onChange={e => setInstance(e.target.value)}>
        <option value="">All instances</option>{instances.map(name => <option key={name}>{name}</option>)}
      </select></label>
      <label>Severity<select value={severity} onChange={e => setSeverity(e.target.value as typeof severity)}>
        <option value="">All</option><option value="CRITICAL">Critical</option><option value="WARNING">Warning</option>
      </select></label>
      <label className="alerts-toolbar-grow">Search<input placeholder="Job, database, login…" value={search} onChange={e => setSearch(e.target.value)} /></label>
    </div>

    {!shown.length ? <EmptyPanel title={events.length ? "No events match these filters" : "No events yet"}>
      Event alerts (deadlocks, failed jobs, restarts, failed logins…) appear here once each.
    </EmptyPanel> : <section className="panel-card alerts-card">
      {shown.map(e => <div key={e.alert_event_id} className="alerts-event-row">
        <span className="alerts-muted" title={new Date(e.occurred_at).toLocaleString()}>{timeAgo(e.occurred_at)}</span>
        <SeverityTag severity={e.severity} />
        <div className="alerts-open-name"><span>{byKey.get(e.alert_key)?.name ?? e.alert_key}</span><span className="alerts-muted">{e.instance_name}</span></div>
        <span className="alerts-detail">{e.detail}</span>
      </div>)}
    </section>}
  </div>;
}
