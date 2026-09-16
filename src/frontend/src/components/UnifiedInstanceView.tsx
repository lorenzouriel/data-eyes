import { useEffect, useState, type ReactNode } from "react";
import { getInstanceOverview } from "../api";
import { statusColorVar, tagStyle } from "../strata";
import type { InstanceHealth, InstanceOverview } from "../types";
import AdvisorTab from "./instance-tabs/AdvisorTab";
import BlockingTab from "./instance-tabs/BlockingTab";
import ResourcesTab from "./instance-tabs/ResourcesTab";
import SessionsTab from "./instance-tabs/SessionsTab";
import SqlTab from "./instance-tabs/SqlTab";
import WaitsTab from "./instance-tabs/WaitsTab";

const SECTIONS = [
  ["resources", "Resources"],
  ["waits", "Waits"],
  ["blocking", "Blocking"],
  ["sessions", "Sessions"],
  ["sql", "SQL"],
  ["advisor", "Advisor"],
] as const;

function Section({ id, title, description, children }: { id: string; title: string; description: string; children: ReactNode }) {
  return (
    <section id={id} className="dashboard-section">
      <div className="dashboard-section-heading">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <a href="#dashboard-top" className="dashboard-back-link">Back to top</a>
      </div>
      {children}
    </section>
  );
}

export default function UnifiedInstanceView({ instance }: { instance: InstanceHealth }) {
  const [overview, setOverview] = useState<InstanceOverview | null | undefined>(undefined);

  useEffect(() => {
    setOverview(undefined);
    getInstanceOverview(instance.name).then(setOverview).catch(() => setOverview(null));
  }, [instance.name]);

  const server = overview?.server.data;
  const waitPct = instance.metrics["wait_stats.Percentage_WaitTime"];
  const alerts = Object.values(instance.categories).filter((severity) => severity === "WARNING" || severity === "CRITICAL").length;

  return (
    <div id="instance-dashboard" className="instance-dashboard">
      <div className="instance-dashboard-header">
        <div>
          <span className="eyebrow">SELECTED INSTANCE</span>
          <div className="instance-dashboard-title">
            <span className="status-dot" style={{ width: 9, height: 9, background: statusColorVar(instance.overall_severity) }} />
            <h2>{instance.label}</h2>
            <span className="tag" style={tagStyle(statusColorVar(instance.overall_severity))}>{instance.overall_severity}</span>
          </div>
          <p>{instance.environment ?? instance.name} · {server?.MachineName ?? instance.name}</p>
        </div>
        <div className="instance-kpis">
          <div><span>WAIT</span><strong>{waitPct === undefined ? "—" : `${waitPct.toFixed(0)}%`}</strong></div>
          <div><span>CORES</span><strong>{server?.Cores ?? "—"}</strong></div>
          <div><span>DATABASES</span><strong>{instance.database_count ?? "—"}</strong></div>
          <div><span>ALERTS</span><strong>{alerts}</strong></div>
        </div>
      </div>

      {overview === undefined && <div className="page-loading">Loading instance summary…</div>}
      {overview === null && <div className="banner-error">The instance summary is currently unavailable.</div>}

      <div className="category-strip" aria-label="Health categories">
        {Object.entries(instance.categories).map(([category, severity]) => (
          <div key={category} className="category-chip">
            <span className="status-dot" style={{ background: statusColorVar(severity) }} />
            <span>{category.replace(/_/g, " ")}</span>
            <strong>{severity}</strong>
          </div>
        ))}
      </div>

      <nav className="dashboard-jump-nav" aria-label="Dashboard sections">
        {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
      </nav>

      <Section id="resources" title="Resources" description="CPU, memory efficiency, throughput, and availability-group pressure.">
        <ResourcesTab instanceName={instance.name} />
      </Section>
      <Section id="waits" title="Waits" description="Current bottlenecks and how wait categories have changed over time.">
        <WaitsTab instanceName={instance.name} />
      </Section>
      <Section id="blocking" title="Blocking" description="Active blocking chains and recently collected blocking events.">
        <BlockingTab instanceName={instance.name} />
      </Section>
      <Section id="sessions" title="Sessions and users" description="Active work grouped by login, program, and host.">
        <SessionsTab instanceName={instance.name} />
      </Section>
      <Section id="sql" title="SQL statements" description="Costly statements, execution characteristics, and plan inspection.">
        <SqlTab instanceName={instance.name} />
      </Section>
      <Section id="advisor" title="Advisor" description="Optional generated interpretation of the evidence shown above.">
        <AdvisorTab instanceName={instance.name} autoLoad={false} />
      </Section>
    </div>
  );
}
