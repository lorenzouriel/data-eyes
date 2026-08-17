import { useEffect, useState, useCallback } from "react";
import { useParams, Link, Navigate } from "react-router-dom";
import { getDatabaseTab, tabInsightStreamUrl, ApiError } from "../api";
import type { TabResponse } from "../types";
import TabSection from "../components/TabSection";
import TrendStrip from "../components/TrendStrip";
import PageInsight from "../components/PageInsight";
import ExplainPanel from "../components/ExplainPanel";
import Logo from "../components/Logo";

// Matches the tab slugs registered in dashboard/backend/app/routers/databases.py
// (TAB_BUILDERS) — keep these two lists in sync if a tab is added/renamed.
const TABS = [
  { key: "wait-time", label: "Wait Time" },
  { key: "top-sql", label: "Top SQL" },
  { key: "storage", label: "Storage" },
  { key: "sessions-blocking", label: "Sessions / Blocking" },
  { key: "config-alerts", label: "Config / Alerts" },
  { key: "index-buffer", label: "Index & Buffer" },
  { key: "ag", label: "Availability Group" },
];

// section key -> title; section keys match the backend tab builders' result
// dict keys exactly (e.g. _top_sql returns {"top_queries": ..., "missing_indexes": ...}).
const TAB_SECTIONS: Record<string, { key: string; title: string }[]> = {
  "wait-time": [{ key: "wait_stats", title: "Wait Statistics" }],
  "top-sql": [
    { key: "top_queries", title: "Top Queries by Duration" },
    { key: "missing_indexes", title: "Missing Indexes" },
  ],
  storage: [{ key: "db_space", title: "Database Files & Drive Space" }],
  "sessions-blocking": [{ key: "blocking", title: "Active Blocking" }],
  "config-alerts": [
    { key: "backup_health", title: "Backup Health" },
    { key: "checkdb_health", title: "CHECKDB Health" },
    { key: "job_health", title: "SQL Agent Jobs" },
  ],
  "index-buffer": [
    { key: "index_fragmentation", title: "Index Fragmentation" },
    { key: "unused_indexes", title: "Unused Indexes" },
    { key: "stale_statistics", title: "Stale Statistics" },
  ],
  ag: [{ key: "ag_health", title: "Availability Group Sync" }],
};

// Trend history (Phase 4) is collected per-INSTANCE, not per-database — a
// database's tab still shows its instance's trend, clearly labeled as such,
// since that's the granularity fleet_health_score's rollup operates at. Only
// wired up for the three categories with the clearest single headline
// metric; the rest are tabular-only for now (see dba_tools.py's metric_specs).
const TAB_TREND: Record<string, { category: string; title: string } | undefined> = {
  "wait-time": { category: "wait_stats", title: "Wait Pressure — Instance Trend" },
  storage: { category: "db_space", title: "Disk Free Space — Instance Trend" },
  "config-alerts": { category: "backup_health", title: "Backup Age — Instance Trend" },
};

export default function DatabaseDrillDown() {
  const { instanceName = "", databaseName = "", tab } = useParams();
  const activeTab = tab && TAB_SECTIONS[tab] ? tab : "wait-time";

  const [data, setData] = useState<TabResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    getDatabaseTab(instanceName, databaseName, activeTab)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load tab"));
  }, [instanceName, databaseName, activeTab]);

  useEffect(() => {
    load();
  }, [load]);

  // Redirect an unknown/stale tab slug to the default rather than 404-ing —
  // bookmarks and typos both land somewhere useful.
  if (tab && !TAB_SECTIONS[tab]) {
    return (
      <Navigate
        to={`/instances/${encodeURIComponent(instanceName)}/db/${encodeURIComponent(databaseName)}/wait-time`}
        replace
      />
    );
  }

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar-brand">
          <Logo className="brand-mark" />
          <span className="brand-name">Data Eyes</span>
        </div>
        <Link className="btn-ghost" to="/">
          ← Fleet
        </Link>
      </header>

      <main className="main-content">
        <div className="main-heading">
          <h1>
            {databaseName} <span className="heading-sub">on {instanceName}</span>
          </h1>
        </div>

        <nav className="tab-nav">
          {TABS.map((t) => (
            <Link
              key={t.key}
              to={`/instances/${encodeURIComponent(instanceName)}/db/${encodeURIComponent(databaseName)}/${t.key}`}
              className={`tab-link ${t.key === activeTab ? "tab-link--active" : ""}`}
            >
              {t.label}
            </Link>
          ))}
        </nav>

        {error && <div className="banner-error">{error}</div>}

        <div className="explain-panel-row">
          <ExplainPanel instanceName={instanceName} databaseName={databaseName} tabName={activeTab} />
        </div>

        <PageInsight
          key={`${instanceName}/${databaseName}/${activeTab}`}
          streamUrl={tabInsightStreamUrl(instanceName, databaseName, activeTab)}
        />

        {TAB_TREND[activeTab] && (
          <TrendStrip
            instanceName={instanceName}
            category={TAB_TREND[activeTab]!.category}
            title={TAB_TREND[activeTab]!.title}
            hours={24}
          />
        )}

        <div className="tab-body">
          {TAB_SECTIONS[activeTab].map((section) => (
            <TabSection key={section.key} title={section.title} result={data?.[section.key]} />
          ))}
        </div>
      </main>
    </div>
  );
}
