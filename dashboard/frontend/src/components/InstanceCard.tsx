import { Link } from "react-router-dom";
import type { InstanceHealth } from "../types";
import StatusBadge from "./StatusBadge";
import TrendStrip from "./TrendStrip";

// Matches .claude/knowledge-base/_static/taxonomy.md's category names —
// keep these two lists in sync if new MCP diagnostic tools are added.
const CATEGORY_LABELS: Record<string, string> = {
  wait_stats: "Wait Stats",
  index_fragmentation: "Index Fragmentation",
  db_space: "Disk Space",
  backup_health: "Backup Health",
  checkdb_health: "CHECKDB",
  blocking: "Blocking",
  ag_health: "Availability Group",
  job_health: "SQL Agent Jobs",
};

export default function InstanceCard({ instance }: { instance: InstanceHealth }) {
  return (
    <Link
      to={`/instances/${encodeURIComponent(instance.name)}`}
      className={`instance-card instance-card--${instance.overall_severity.toLowerCase()}`}
    >
      <div className="instance-card-header">
        <div>
          <h2>{instance.label}</h2>
          {instance.environment && <span className="instance-env">{instance.environment}</span>}
        </div>
        <StatusBadge severity={instance.overall_severity} />
      </div>

      {instance.reachable ? (
        <>
          <div className="instance-meta">
            {instance.database_count !== null && (
              <span>
                {instance.database_count} database{instance.database_count === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {Object.keys(instance.categories).length > 0 && (
            <ul className="category-list">
              {Object.entries(instance.categories).map(([key, severity]) => (
                <li key={key}>
                  <span className="category-name">{CATEGORY_LABELS[key] ?? key}</span>
                  <StatusBadge severity={severity} />
                </li>
              ))}
            </ul>
          )}
          <TrendStrip instanceName={instance.name} category="overall" hours={24} />
        </>
      ) : (
        <div className="instance-error">{instance.error ?? "Instance unreachable"}</div>
      )}
    </Link>
  );
}
