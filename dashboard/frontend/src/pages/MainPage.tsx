import { useEffect, useState, useCallback } from "react";
import { useAuth } from "../auth/AuthContext";
import { getFleetHealth, fleetInsightStreamUrl } from "../api";
import type { FleetHealth } from "../types";
import StatusBadge from "../components/StatusBadge";
import InstanceCard from "../components/InstanceCard";
import PageInsight from "../components/PageInsight";
import InsightsFeed from "../components/InsightsFeed";
import Logo from "../components/Logo";

const POLL_INTERVAL_MS = 30_000;

export default function MainPage() {
  const { username, logout } = useAuth();
  const [fleet, setFleet] = useState<FleetHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

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

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar-brand">
          <Logo className="brand-mark" />
          <span className="brand-name">Data Eyes</span>
        </div>
        <div className="topbar-right">
          {fleet && <StatusBadge severity={fleet.overall_severity} label="Fleet" />}
          <span className="topbar-user">{username}</span>
          <button className="btn-ghost" onClick={() => logout()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="main-heading">
          <h1>Fleet Overview</h1>
          {lastUpdated && <span className="last-updated">Updated {lastUpdated.toLocaleTimeString()}</span>}
        </div>

        {error && <div className="banner-error">{error}</div>}

        {!fleet && !error && <div className="page-loading">Loading fleet…</div>}

        {fleet && <PageInsight streamUrl={fleetInsightStreamUrl()} />}

        <InsightsFeed />

        {fleet && (
          <div className="instance-grid">
            {fleet.instances.map((instance) => (
              <InstanceCard key={instance.name} instance={instance} />
            ))}
            {fleet.instances.length === 0 && (
              <div className="empty-state">
                No instances configured — add entries to <code>dashboard/backend/instances.yaml</code>.
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
