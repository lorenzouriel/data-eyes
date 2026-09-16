import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import UnifiedInstanceView from "../components/UnifiedInstanceView";
import { getFleetHealth } from "../api";
import type { InstanceHealth } from "../types";

const POLL_INTERVAL_MS = 30_000;
const VALID_SECTIONS = new Set(["resources", "waits", "blocking", "sessions", "sql", "advisor"]);

export default function InstanceDashboard() {
  const { instanceName = "", tab } = useParams();
  const navigate = useNavigate();
  const [instance, setInstance] = useState<InstanceHealth | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fleet = await getFleetHealth();
      const match = fleet.instances.find((item) => item.name === instanceName) ?? null;
      setInstance(match);
      setError(match ? null : `Instance "${instanceName}" was not found.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load instance health");
      setInstance(null);
    }
  }, [instanceName]);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!instance || !tab || !VALID_SECTIONS.has(tab)) return;
    const frame = window.requestAnimationFrame(() => document.getElementById(tab)?.scrollIntoView({ block: "start" }));
    return () => window.cancelAnimationFrame(frame);
  }, [instance, tab]);

  return (
    <AppShell active="status">
      <div id="dashboard-top" className="page-inner">
        <div className="instance-page-toolbar">
          <button className="btn-ghost" onClick={() => navigate("/")}>← All instances</button>
          <span className="page-subtitle">Full instance dashboard</span>
        </div>

        {instance === undefined && <div className="page-loading">Loading instance dashboard…</div>}
        {error && <div className="banner-error">{error}</div>}
        {instance && <UnifiedInstanceView key={instance.name} instance={instance} />}
      </div>
    </AppShell>
  );
}
