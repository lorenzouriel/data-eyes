import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppShell from "../../../app/AppShell";
import { useAuth } from "../../auth/AuthContext";
import { getInstances } from "../../instances/api";
import type { InstanceSummary } from "../../instances/types";
import { getNotificationChannels } from "../../notifications/api";
import type { NotificationChannel } from "../../notifications/types";
import { getAlertCatalog, getAlertEvents, getAlertStates, getDigestSetting, resetAlertSetting, saveAlertSetting, saveDigestSetting } from "../api";
import AlertEvents from "../components/AlertEvents";
import AlertSettings from "../components/AlertSettings";
import AlertsOverview from "../components/AlertsOverview";
import DigestSettings from "../components/DigestSettings";
import type { AlertCatalog, AlertEvent, AlertSetting, AlertState, DigestSetting } from "../types";

type TabKey = "overview" | "events" | "settings" | "checklist";

export default function Alerts() {
  const { role } = useAuth();
  const admin = role === "admin";
  const navigate = useNavigate();
  const { tab } = useParams();
  const [catalog, setCatalog] = useState<AlertCatalog>();
  const [states, setStates] = useState<AlertState[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [digest, setDigest] = useState<DigestSetting>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    const [c, s, e, i] = await Promise.all([getAlertCatalog(), getAlertStates(), getAlertEvents(200), getInstances()]);
    setCatalog(c); setStates(s); setEvents(e); setInstances(i);
    if (admin) {
      const [ch, d] = await Promise.all([getNotificationChannels(), getDigestSetting()]);
      setChannels(ch); setDigest(d);
    }
  }, [admin]);
  useEffect(() => {
    refresh().catch(e => setError(e instanceof Error ? e.message : "Could not load alerts"));
    // Open alerts and events change every collector cycle.
    const timer = window.setInterval(() => { refresh().catch(() => undefined); }, 60_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(message); return true; }
    catch (e) { setError(e instanceof Error ? e.message : "Request failed"); return false; }
    finally { setBusy(false); }
  };

  const byKey = useMemo(() => new Map(catalog?.alerts.map(a => [a.key, a]) ?? []), [catalog]);
  const openCount = states.filter(s => s.severity === "WARNING" || s.severity === "CRITICAL").length;
  const tabs: { key: TabKey; label: string; count?: number }[] = [
    { key: "overview", label: "Overview", count: openCount },
    { key: "events", label: "Events", count: events.length || undefined },
    { key: "settings", label: "Settings" },
    ...(admin ? [{ key: "checklist" as TabKey, label: "Daily checklist" }] : []),
  ];
  const active: TabKey = tabs.some(t => t.key === tab) ? tab as TabKey : "overview";

  return <AppShell active="alerts">
    <div className="alerts-page">
      <div className="alerts-header">
        <div className="alerts-header-inner">
          <div className="alerts-header-text">
            <h1 className="page-title">Alerts</h1>
            <p className="page-subtitle">What needs attention across the fleet, and which checks run. Delivery is set up on Notifications.</p>
          </div>
          <nav className="alerts-tabs" aria-label="Alerts sections">
            {tabs.map(t => <button key={t.key} type="button" className={`alerts-tab${active === t.key ? " active" : ""}`}
              aria-current={active === t.key ? "page" : undefined} onClick={() => navigate(`/alerts/${t.key}`)}>
              {t.label}{t.count ? <span className="alerts-tab-count">{t.count}</span> : null}
            </button>)}
          </nav>
        </div>
      </div>
      <div className="alerts-body">
        {error && <p role="alert" className="banner-error">{error}</p>}
        {notice && <p role="status" className="banner-success">{notice}</p>}
        {!catalog && !error && <p className="page-loading">Loading alerts…</p>}
        {catalog && active === "overview" && <AlertsOverview states={states} events={events} byKey={byKey} instanceCount={instances.length} />}
        {catalog && active === "events" && <AlertEvents events={events} byKey={byKey} />}
        {catalog && active === "settings" && <AlertSettings catalog={catalog} instances={instances} admin={admin} busy={busy}
          save={(setting: AlertSetting, message: string) => run(() => saveAlertSetting(setting), message)}
          reset={(key: string, instance: string, message: string) => run(() => resetAlertSetting(key, instance), message)} />}
        {catalog && active === "checklist" && digest && <DigestSettings digest={digest} channels={channels} busy={busy}
          save={setting => run(() => saveDigestSetting(setting), "Daily checklist saved.")} />}
      </div>
    </div>
  </AppShell>;
}
