import { useEffect, useState, type ReactNode } from "react";
import { getInstanceOverview } from "../api";
import { statusColorVar, tagStyle } from "../strata";
import type { InstanceHealth, InstanceOverview } from "../types";
import AdvisorTab from "./instance-tabs/AdvisorTab";
import ResourcesTab from "./instance-tabs/ResourcesTab";
import DatabasesTab from "./instance-tabs/DatabasesTab";
import TopActivityTab from "./instance-tabs/TopActivityTab";
import StatusSummaryPanel from "./StatusSummaryPanel";

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
      <div className="instance-dashboard-header" style={{ flexDirection: "column", alignItems: "stretch", gap: 18 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24, flexWrap: "wrap" }}>
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
        <ResourcesTab instanceName={instance.name} />
      </div>

      {overview === undefined && <div className="page-loading">Loading instance summary…</div>}
      {overview === null && <div className="banner-error">The instance summary is currently unavailable.</div>}

      <StatusSummaryPanel variant="instance" categories={instance.categories} />

      <Section id="databases" title="Databases" description="Database access mode and Always On availability group membership on this instance. Access mode does not describe the monitoring login's permissions.">
        <DatabasesTab instanceName={instance.name} />
      </Section>
      <Section id="activity" title="Top activity" description="Top-10 history by wait time (Waits, Programs, Databases, Machines, DB Users, Files, Drives, Plans, SQL Statements, Blocking Statements) and Deadlocks, over 30 days, 7 days, or a specific day's activity.">
        <TopActivityTab instanceName={instance.name} />
      </Section>
      <Section id="advisor" title="Advisor" description="Optional generated interpretation of the evidence shown above.">
        <AdvisorTab instanceName={instance.name} autoLoad={false} />
      </Section>
    </div>
  );
}
