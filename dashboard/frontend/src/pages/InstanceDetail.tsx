import { useEffect, useState } from "react";
import { useNavigate, useParams, Navigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import WaitsTab from "../components/instance-tabs/WaitsTab";
import BlockingTab from "../components/instance-tabs/BlockingTab";
import SessionsTab from "../components/instance-tabs/SessionsTab";
import SqlTab from "../components/instance-tabs/SqlTab";
import ResourcesTab from "../components/instance-tabs/ResourcesTab";
import AdvisorTab from "../components/instance-tabs/AdvisorTab";
import { getInstanceOverview } from "../api";
import { statusColorVar } from "../strata";
import type { InstanceOverview } from "../types";

const TABS = [
  { key: "waits", label: "Wait types" },
  { key: "blocking", label: "Blocking" },
  { key: "sessions", label: "Sessions & users" },
  { key: "sql", label: "SQL statements" },
  { key: "resources", label: "Resources" },
  { key: "advisor", label: "Advisor" },
];

export default function InstanceDetail() {
  const { instanceName = "", tab } = useParams();
  const navigate = useNavigate();
  const activeTab = tab && TABS.some((t) => t.key === tab) ? tab : "waits";
  const [overview, setOverview] = useState<InstanceOverview | null | undefined>(undefined);

  useEffect(() => {
    setOverview(undefined);
    getInstanceOverview(instanceName)
      .then(setOverview)
      .catch(() => setOverview(null));
  }, [instanceName]);

  if (tab && !TABS.some((t) => t.key === tab)) {
    return <Navigate to={`/instances/${encodeURIComponent(instanceName)}/waits`} replace />;
  }

  const health = overview?.health.data;
  const server = overview?.server.data;
  const alertCount = health ? Object.values(health.categories).filter((s) => s === "WARNING" || s === "CRITICAL").length : 0;

  return (
    <AppShell active="status">
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100%" }}>
        <div style={{ flex: "none", background: "var(--panel)", borderBottom: "1px solid var(--line)", padding: "16px 24px 0" }}>
          <div style={{ maxWidth: 1500, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate("/");
                  }}
                  style={{ fontSize: 11.5, color: "var(--muted)" }}
                >
                  ← All instances
                </a>
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
                  <span className="status-dot" style={{ width: 9, height: 9, background: statusColorVar(health?.overall_severity ?? "UNKNOWN") }} />
                  <h1 style={{ margin: 0, font: "600 21px 'Space Grotesk', sans-serif", letterSpacing: "-.5px" }}>{instanceName}</h1>
                  {server?.ProductVersion && (
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)", border: "1px solid var(--line)", borderRadius: 4, padding: "2px 6px" }}>
                      {server.Edition ?? server.ProductVersion}
                    </span>
                  )}
                </div>
              </div>
              <div style={{ display: "flex", gap: 20 }}>
                {[
                  ["WAIT", health?.metrics?.["wait_stats.Percentage_WaitTime"] !== undefined ? `${health.metrics["wait_stats.Percentage_WaitTime"].toFixed(0)}%` : "—"],
                  ["CORES", server?.Cores ?? "—"],
                  ["ALERTS", overview ? String(alertCount) : "—"],
                ].map(([label, value]) => (
                  <div key={label} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <span className="mono" style={{ fontSize: 9.5, letterSpacing: "0.09em", color: "var(--muted)" }}>{label}</span>
                    <span style={{ font: "600 18px 'Space Grotesk', sans-serif", letterSpacing: "-.4px" }}>{value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ display: "flex", gap: 4, overflowX: "auto" }}>
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => navigate(`/instances/${encodeURIComponent(instanceName)}/${t.key}`)}
                  style={{
                    font: "500 12.5px 'Space Grotesk', sans-serif",
                    whiteSpace: "nowrap",
                    padding: "9px 13px",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    borderBottom: `2px solid ${activeTab === t.key ? "var(--accent)" : "transparent"}`,
                    color: activeTab === t.key ? "var(--text)" : "var(--muted)",
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div style={{ flex: 1, padding: "22px 24px 44px" }}>
          <div style={{ maxWidth: 1500, margin: "0 auto" }}>
            {activeTab === "waits" && <WaitsTab instanceName={instanceName} />}
            {activeTab === "blocking" && <BlockingTab instanceName={instanceName} />}
            {activeTab === "sessions" && <SessionsTab instanceName={instanceName} />}
            {activeTab === "sql" && <SqlTab instanceName={instanceName} />}
            {activeTab === "resources" && <ResourcesTab instanceName={instanceName} />}
            {activeTab === "advisor" && <AdvisorTab instanceName={instanceName} />}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
