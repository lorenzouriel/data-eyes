import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { useAuth } from "../auth/AuthContext";
import { deleteNotification, getNotificationChannels, getNotificationLogs, getNotificationRules, saveNotificationChannel, saveNotificationRule, testNotificationChannel } from "../api";
import type { NotificationChannel, NotificationChannelType, NotificationLog, NotificationRule } from "../types";

const secrets = new Set(["webhook_url", "username", "password", "account_sid", "auth_token"]);
const fields: Record<NotificationChannelType, string[]> = {
  slack: ["webhook_url", "channel", "mention"], teams: ["webhook_url"],
  email: ["smtp_host", "port", "username", "password", "from_addr", "to_addrs"],
  sms: ["account_sid", "auth_token", "from_number", "to_numbers"],
};
const optional = new Set(["channel", "mention", "username", "password"]);
const blankChannel = (): Omit<NotificationChannel, "id"> => ({ name: "", type: "slack", enabled: true, config: {} });
const blankRule = (channel_id: number): Omit<NotificationRule, "id"> => ({
  name: "", channel_id, enabled: true, instance: null, category: null, severities: ["CRITICAL"], recovery: false,
  cooldown_seconds: null, quiet_start: null, quiet_end: null, group_by_instance: false,
});
const formStyle = { padding: 16, display: "flex", flexDirection: "column" as const, gap: 12, marginBottom: 20 };

function NotificationManager() {
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [logs, setLogs] = useState<NotificationLog[]>([]);
  const [offset, setOffset] = useState(0);
  const [channel, setChannel] = useState(blankChannel);
  const [channelId, setChannelId] = useState<number>();
  const [rule, setRule] = useState(() => blankRule(0));
  const [ruleId, setRuleId] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = useCallback(async () => {
    const [c, r, l] = await Promise.all([getNotificationChannels(), getNotificationRules(), getNotificationLogs(offset)]);
    setChannels(c); setRules(r); setLogs(l);
    setRule(old => old.channel_id ? old : { ...old, channel_id: c[0]?.id ?? 0 });
  }, [offset]);
  useEffect(() => {
    setLoading(true);
    refresh().catch(e => setError(String(e.message))).finally(() => setLoading(false));
  }, [refresh]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  };
  const updateConfig = (key: string, value: string | boolean) => setChannel(c => ({ ...c, config: { ...c.config, [key]: value } }));
  const submitChannel = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const config = { ...channel.config };
      if (channel.type === "email") {
        config.port = Number(config.port ?? 587); config.use_tls = config.use_tls ?? true;
        config.to_addrs = Array.isArray(config.to_addrs) ? config.to_addrs : String(config.to_addrs ?? "").split(",").map(s => s.trim()).filter(Boolean);
      }
      if (channel.type === "sms") {
        config.provider = "twilio";
        config.to_numbers = Array.isArray(config.to_numbers) ? config.to_numbers : String(config.to_numbers ?? "").split(",").map(s => s.trim()).filter(Boolean);
        if (![config.from_number, ...config.to_numbers].every(n => /^\+[1-9]\d{1,14}$/.test(String(n)))) throw new Error("Phone numbers must use E.164, for example +15551234567.");
      }
      // Omitted secrets on edit preserve the saved values.
      if (channelId) for (const key of secrets) if (config[key] === "") delete config[key];
      await saveNotificationChannel({ ...channel, config }, channelId);
      setChannel(blankChannel()); setChannelId(undefined); setNotice("Channel saved.");
    });
  };
  const editChannel = (c: NotificationChannel) => {
    const config = { ...c.config };
    for (const key of secrets) if (config[key] === "********") config[key] = "";
    setChannel({ name: c.name, type: c.type, enabled: c.enabled, config }); setChannelId(c.id);
  };
  const remove = (kind: "channels" | "rules" | "logs", id: number) => {
    if (window.confirm(kind === "channels" ? "Delete this channel and its rules?" : `Delete this ${kind === "rules" ? "rule" : "log entry"}?`)) void run(async () => { await deleteNotification(kind, id); });
  };
  const editRule = (r: NotificationRule) => {
    // Avoid returning repository metadata such as created_at in write requests.
    const { name, channel_id, enabled, instance, category, severities, recovery, cooldown_seconds, quiet_start, quiet_end, group_by_instance } = r;
    setRule({ name, channel_id, enabled, instance, category, severities, recovery, cooldown_seconds, quiet_start, quiet_end, group_by_instance }); setRuleId(r.id);
  };
  return <AppShell active="notifications"><main className="notifications-page" style={{ padding: 24, maxWidth: 1300, margin: "0 auto" }}>
    <h1>Notifications</h1>
    <p>Send health transitions to Slack, Teams, email or SMS. The first sample establishes a baseline. Quiet hours use UTC.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {loading && <p role="status">Loading notifications…</p>}
    <h2>Channels</h2>
    <form className="field panel-card" style={formStyle} onSubmit={submitChannel}>
      <h3>{channelId ? "Edit channel" : "Add channel"}</h3>
      <label>Name<input required maxLength={120} value={channel.name} onChange={e => setChannel({ ...channel, name: e.target.value })} /></label>
      <label>Type<select value={channel.type} disabled={!!channelId} onChange={e => setChannel({ ...channel, type: e.target.value as NotificationChannelType, config: {} })}>
        <option value="slack">Slack</option><option value="teams">Teams Workflows</option><option value="email">Email</option><option value="sms">SMS (Twilio)</option>
      </select></label>
      {fields[channel.type].map(key => <label key={key}>{key.replace(/_/g, " ")}{channelId && secrets.has(key) ? " (leave blank to keep saved value)" : ""}
        <input type={secrets.has(key) ? "password" : key === "port" ? "number" : "text"} autoComplete="off"
          min={key === "port" ? 1 : undefined} max={key === "port" ? 65535 : undefined}
          required={!optional.has(key) && !(channelId && secrets.has(key))}
          placeholder={key === "to_addrs" || key === "to_numbers" ? "Separate recipients with commas" : key === "from_number" ? "+15551234567" : ""}
          value={Array.isArray(channel.config[key]) ? (channel.config[key] as string[]).join(", ") : String(channel.config[key] ?? (key === "port" ? 587 : ""))}
          onChange={e => updateConfig(key, e.target.value)} />
      </label>)}
      {channel.type === "email" && <label><input type="checkbox" checked={channel.config.use_tls !== false} onChange={e => updateConfig("use_tls", e.target.checked)} /> Use TLS (implicit on port 465, STARTTLS otherwise)</label>}
      {channel.type === "sms" && <p>Twilio charges apply, including tests. New rules default to CRITICAL-only with recovery off.</p>}
      <label><input type="checkbox" checked={channel.enabled} onChange={e => setChannel({ ...channel, enabled: e.target.checked })} /> Enabled</label>
      <div><button disabled={busy} type="submit">Save channel</button> {channelId && <button type="button" onClick={() => { setChannel(blankChannel()); setChannelId(undefined); }}>Cancel edit</button>}</div>
    </form>
    <div style={{ overflowX: "auto" }}><table className="data-table"><thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {channels.map(c => <tr key={c.id}><td>{c.name}</td><td>{c.type}</td><td>{c.enabled ? "Enabled" : "Disabled"}</td><td>
        <button disabled={busy} onClick={() => editChannel(c)}>Edit</button>{" "}
        <button disabled={busy} onClick={() => void run(async () => { const result = await testNotificationChannel(c.id); setNotice(`${c.name}: ${result.ok ? "Test sent" : result.message}`); })}>Send test</button>{" "}
        <button disabled={busy} onClick={() => remove("channels", c.id)}>Delete</button>
      </td></tr>)}
      {!channels.length && <tr><td colSpan={4}>No channels configured.</td></tr>}
    </tbody></table></div>
    <h2>Rules</h2>
    <form className="field panel-card" style={formStyle} onSubmit={e => { e.preventDefault(); void run(async () => { await saveNotificationRule(rule, ruleId); setRule(blankRule(channels[0]?.id ?? 0)); setRuleId(undefined); setNotice("Rule saved."); }); }}>
      <h3>{ruleId ? "Edit rule" : "Add rule"}</h3>
      <label>Name<input required maxLength={120} value={rule.name} onChange={e => setRule({ ...rule, name: e.target.value })} /></label>
      <label>Channel<select required value={rule.channel_id || ""} onChange={e => setRule({ ...rule, channel_id: Number(e.target.value), severities: ["CRITICAL"], recovery: false })}>
        <option value="" disabled>Select channel</option>{channels.map(c => <option key={c.id} value={c.id}>{c.name} ({c.type})</option>)}
      </select></label>
      <label>Instance (blank matches all)<input value={rule.instance ?? ""} onChange={e => setRule({ ...rule, instance: e.target.value || null })} /></label>
      <label>Category (blank matches all)<input placeholder="backup, errors, overall…" value={rule.category ?? ""} onChange={e => setRule({ ...rule, category: e.target.value || null })} /></label>
      <fieldset><legend>New severity</legend>{["WARNING", "CRITICAL", "UNKNOWN"].map(s => <label key={s} style={{ marginRight: 16 }}><input type="checkbox" checked={rule.severities.includes(s)} onChange={e => setRule({ ...rule, severities: e.target.checked ? [...rule.severities, s] : rule.severities.filter(v => v !== s) })} /> {s}</label>)}</fieldset>
      <label><input type="checkbox" checked={rule.recovery} onChange={e => setRule({ ...rule, recovery: e.target.checked })} /> Include recovery to OK</label>
      <label>Cooldown (seconds; blank uses server default)<input type="number" min={0} max={604800} value={rule.cooldown_seconds ?? ""} onChange={e => setRule({ ...rule, cooldown_seconds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
      <div style={{ display: "flex", gap: 16 }}>{(["quiet_start", "quiet_end"] as const).map(key => <label key={key}>{key === "quiet_start" ? "Quiet hours start" : "Quiet hours end"} (UTC, 0–23)
        <input type="number" min={0} max={23} value={rule[key] ?? ""} onChange={e => setRule({ ...rule, [key]: e.target.value === "" ? null : Number(e.target.value) })} />
      </label>)}</div>
      <label><input type="checkbox" checked={rule.group_by_instance} onChange={e => setRule({ ...rule, group_by_instance: e.target.checked })} /> Group matching transitions per instance per cycle (email digest)</label>
      <label><input type="checkbox" checked={rule.enabled} onChange={e => setRule({ ...rule, enabled: e.target.checked })} /> Enabled</label>
      <div><button disabled={busy || !channels.length || !rule.severities.length} type="submit">Save rule</button> {ruleId && <button type="button" onClick={() => { setRule(blankRule(channels[0]?.id ?? 0)); setRuleId(undefined); }}>Cancel edit</button>}</div>
    </form>
    <p>Cooldown and quiet hours suppress a transition permanently; skipped deliveries appear in the log. Overlapping rules each send independently.</p>
    <div style={{ overflowX: "auto" }}><table className="data-table"><thead><tr><th>Name</th><th>Channel</th><th>Match</th><th>Severity</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {rules.map(r => <tr key={r.id}><td>{r.name}</td><td>{channels.find(c => c.id === r.channel_id)?.name}</td><td>{r.instance ?? "All instances"} / {r.category ?? "All categories"}</td><td>{r.severities.join(", ")}{r.recovery ? " + recovery" : ""}</td><td>{r.enabled ? "Enabled" : "Disabled"}</td><td><button disabled={busy} onClick={() => editRule(r)}>Edit</button>{" "}<button disabled={busy} onClick={() => remove("rules", r.id)}>Delete</button></td></tr>)}
      {!rules.length && <tr><td colSpan={6}>No rules configured.</td></tr>}
    </tbody></table></div>
    <h2>Delivery log</h2><button disabled={busy} onClick={() => void run(async () => {})}>Refresh</button>
    <div style={{ overflowX: "auto" }}><table className="data-table"><thead><tr><th>Time</th><th>Channel</th><th>Instance / category</th><th>Transition</th><th>Status</th><th>Details</th><th>Actions</th></tr></thead><tbody>
      {logs.map(l => <tr key={l.id}><td>{new Date(l.created_at).toLocaleString()}</td><td>{channels.find(c => c.id === l.channel_id)?.name ?? "Deleted"}</td><td>{l.instance_name} / {l.category === "*" ? "Grouped" : l.category}</td><td>{l.event.old_severity ?? "Initial"} → {l.event.new_severity}</td><td>{l.status}</td><td>{l.message} ({l.attempts} attempts)</td><td><button disabled={busy || ["pending", "sending"].includes(l.status)} onClick={() => remove("logs", l.id)}>Delete</button></td></tr>)}
      {!logs.length && <tr><td colSpan={7}>No deliveries recorded.</td></tr>}
    </tbody></table></div>
    <button disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>{" "}
    <button disabled={busy || logs.length < 50} onClick={() => setOffset(offset + 50)}>Next</button>
  </main></AppShell>;
}

export default function Notifications() {
  const { role } = useAuth();
  return role === "admin" ? <NotificationManager /> : <Navigate to="/" replace />;
}
