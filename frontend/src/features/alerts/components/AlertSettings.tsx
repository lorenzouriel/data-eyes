import { useMemo, useState } from "react";
import type { InstanceSummary } from "../../instances/types";
import type { AlertCatalog, AlertDefinition, AlertSetting, AlertTier } from "../types";
import { EmptyPanel, TIER_LABELS, describeThresholds, inherit } from "./shared";

const FLEET = "";
type Filter = "all" | "on" | "off" | "customized";

interface Draft { warning: string; critical: string; tier: "" | AlertTier; confirm: string; excluded: string }

interface Props {
  catalog: AlertCatalog;
  instances: InstanceSummary[];
  admin: boolean;
  busy: boolean;
  save: (setting: AlertSetting, message: string) => Promise<boolean>;
  reset: (alertKey: string, instance: string, message: string) => Promise<boolean>;
}

const toNumber = (text: string) => text.trim() === "" ? null : Number(text);

function Switch({ checked, disabled, label, onChange }: { checked: boolean; disabled: boolean; label: string; onChange: (value: boolean) => void }) {
  return <label className="alerts-switch" title={label}>
    <input type="checkbox" role="switch" aria-label={label} checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)} />
    <span aria-hidden="true" />
  </label>;
}

export default function AlertSettings({ catalog, instances, admin, busy, save, reset }: Props) {
  const [scope, setScope] = useState(FLEET);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<string>();
  const [draft, setDraft] = useState<Draft>();

  const saved = (key: string, instance: string) => catalog.settings.find(s => s.alert_key === key && s.instance_name === instance);
  const parentRows = (key: string) => scope === FLEET ? [] : [saved(key, FLEET)];
  const scopeLabel = scope === FLEET ? "all instances" : instances.find(i => i.name === scope)?.label || scope;

  const groups = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const result = new Map<string, AlertDefinition[]>();
    for (const a of catalog.alerts) {
      if (scope !== FLEET && a.scope !== "instance") continue;
      if (needle && !`${a.name} ${a.description} ${a.key} ${a.group}`.toLowerCase().includes(needle)) continue;
      const enabled = inherit(a, [...(scope === FLEET ? [] : [saved(a.key, FLEET)]), saved(a.key, scope)]).enabled;
      if ((filter === "on" && !enabled) || (filter === "off" && enabled) || (filter === "customized" && !saved(a.key, scope))) continue;
      result.set(a.group, [...(result.get(a.group) ?? []), a]);
    }
    return result;
  }, [catalog, scope, search, filter]);

  const baseSetting = (a: AlertDefinition): AlertSetting => {
    const row = saved(a.key, scope);
    return { alert_key: a.key, instance_name: scope, enabled: row?.enabled ?? null, warning_threshold: row?.warning_threshold ?? null,
      critical_threshold: row?.critical_threshold ?? null, tier: row?.tier ?? null, confirm_samples: row?.confirm_samples ?? null,
      excluded_databases: row?.excluded_databases ?? null };
  };
  const openEditor = (a: AlertDefinition) => {
    if (editing === a.key) { setEditing(undefined); return; }
    const row = saved(a.key, scope);
    setDraft({ warning: row?.warning_threshold?.toString() ?? "", critical: row?.critical_threshold?.toString() ?? "", tier: row?.tier ?? "",
      confirm: row?.confirm_samples?.toString() ?? "", excluded: row?.excluded_databases?.join(", ") ?? "" });
    setEditing(a.key);
  };
  const submit = async (a: AlertDefinition) => {
    if (!draft) return;
    const excluded = draft.excluded.split(",").map(s => s.trim()).filter(Boolean);
    const ok = await save({
      ...baseSetting(a),
      warning_threshold: a.has_thresholds ? toNumber(draft.warning) : null,
      critical_threshold: a.has_thresholds ? toNumber(draft.critical) : null,
      tier: draft.tier || null,
      confirm_samples: a.kind === "state" ? toNumber(draft.confirm) : null,
      excluded_databases: a.per_database && excluded.length ? excluded : null,
    }, `${a.name} saved for ${scopeLabel}.`);
    if (ok) setEditing(undefined);
  };
  const toggleGroup = (group: string) => setCollapsed(c => { const next = new Set(c); if (next.has(group)) next.delete(group); else next.add(group); return next; });
  const customizedCount = catalog.settings.filter(s => s.instance_name === scope).length;

  return <div className="alerts-stack">
    <div className="alerts-toolbar alerts-toolbar--sticky field">
      <label>Applies to<select value={scope} onChange={e => { setScope(e.target.value); setEditing(undefined); }}>
        <option value={FLEET}>All instances (fleet default)</option>
        {instances.map(i => <option key={i.name} value={i.name}>{i.label || i.name} (override)</option>)}
      </select></label>
      <label className="alerts-toolbar-grow">Search<input placeholder="backup, tempdb, login…" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <div className="alerts-chips" role="group" aria-label="Show">
        {(["all", "on", "off", "customized"] as Filter[]).map(f => <button key={f} type="button"
          className={`alerts-chip${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>
          {f === "all" ? "All" : f === "on" ? "On" : f === "off" ? "Off" : `Customized (${customizedCount})`}
        </button>)}
      </div>
    </div>
    <p className="alerts-hint">
      {scope === FLEET
        ? "Fleet defaults apply to every instance unless an instance overrides them."
        : `Overrides for ${scopeLabel}. Anything left blank follows the fleet default.`}
      {!admin && " Only administrators can change settings."}
    </p>

    {!groups.size && <EmptyPanel title="No alerts match">Clear the search or choose another filter.</EmptyPanel>}

    {[...groups.entries()].map(([group, alerts]) => {
      const isCollapsed = collapsed.has(group);
      const enabledCount = alerts.filter(a => inherit(a, [...parentRows(a.key), saved(a.key, scope)]).enabled).length;
      return <section key={group} className="panel-card alerts-card">
        <button type="button" className="alerts-group-header" aria-expanded={!isCollapsed} onClick={() => toggleGroup(group)}>
          <span className="alerts-caret">{isCollapsed ? "▸" : "▾"}</span>
          <strong>{group}</strong>
          <span className="alerts-muted">{enabledCount} of {alerts.length} on</span>
        </button>
        {!isCollapsed && alerts.map(a => {
          const parent = inherit(a, parentRows(a.key));
          const row = saved(a.key, scope);
          const effective = inherit(a, [...parentRows(a.key), row]);
          const isEditing = editing === a.key && draft;
          return <div key={a.key} className={`alerts-setting${effective.enabled ? "" : " is-off"}${isEditing ? " is-editing" : ""}`}>
            <div className="alerts-setting-row">
              <Switch checked={effective.enabled} disabled={!admin || busy} label={`Turn ${a.name} ${effective.enabled ? "off" : "on"} for ${scopeLabel}`}
                onChange={value => void save({ ...baseSetting(a), enabled: value }, `${a.name} turned ${value ? "on" : "off"} for ${scopeLabel}.`)} />
              <div className="alerts-setting-main">
                <div className="alerts-setting-title">
                  <span>{a.name}</span>
                  <span className="tag alerts-kind">{a.kind === "event" ? "Event" : "State"}</span>
                  {row && <span className="tag alerts-custom">Customized</span>}
                  {scope !== FLEET && row?.enabled != null && <button type="button" className="alerts-link" disabled={!admin || busy}
                    onClick={() => void save({ ...baseSetting(a), enabled: null }, `${a.name} follows the fleet default again.`)}>use fleet on/off</button>}
                </div>
                <div className="alerts-setting-summary">
                  {TIER_LABELS[effective.tier]} · {describeThresholds(a, effective)}
                  {a.kind === "state" && effective.confirm > 1 && ` · confirm ×${effective.confirm}`}
                  {effective.excluded.length > 0 && ` · skips ${effective.excluded.join(", ")}`}
                </div>
                <div className="alerts-setting-description">{a.description}</div>
              </div>
              <button type="button" className="btn-ghost" onClick={() => openEditor(a)} aria-expanded={!!isEditing}>
                {isEditing ? "Close" : admin ? "Configure" : "Details"}
              </button>
            </div>

            {isEditing && <form className="alerts-editor field" onSubmit={e => { e.preventDefault(); void submit(a); }}>
              <label>Frequency<select disabled={!admin} value={draft.tier} onChange={e => setDraft({ ...draft, tier: e.target.value as Draft["tier"] })}>
                <option value="">Default — {TIER_LABELS[parent.tier]}</option>
                {(Object.keys(TIER_LABELS) as AlertTier[]).map(t => <option key={t} value={t}>{TIER_LABELS[t]}</option>)}
              </select></label>
              {a.has_thresholds && (["warning", "critical"] as const).map(level => <label key={level}>
                {level === "warning" ? "Warning" : "Critical"} {a.direction === "above" ? "at or above" : "at or below"}{a.unit ? ` (${a.unit})` : ""}
                <input type="number" step="any" disabled={!admin} placeholder={parent[level] === null ? "none" : `Default ${parent[level]}`}
                  value={draft[level]} onChange={e => setDraft({ ...draft, [level]: e.target.value })} />
              </label>)}
              {a.kind === "state" && <label>Double check (samples in a row)
                <input type="number" min={1} max={10} disabled={!admin} placeholder={`Default ${parent.confirm}`} value={draft.confirm}
                  onChange={e => setDraft({ ...draft, confirm: e.target.value })} />
              </label>}
              {a.per_database && <label className="alerts-editor-wide">Skip these databases (comma-separated)
                <input disabled={!admin} placeholder={parent.excluded.length ? `Already skipped: ${parent.excluded.join(", ")}` : "e.g. Dev, Scratch"}
                  value={draft.excluded} onChange={e => setDraft({ ...draft, excluded: e.target.value })} />
              </label>}
              <p className="alerts-editor-wide alerts-hint">
                Needs <strong>{a.permission}</strong>. Leave a field blank to use the default shown.
              </p>
              {admin && <div className="alerts-editor-wide alerts-editor-actions">
                <button type="submit" className="btn-primary" disabled={busy}>Save</button>
                <button type="button" className="btn-ghost" disabled={busy || !row}
                  onClick={() => void reset(a.key, scope, `${a.name} reset to ${scope === FLEET ? "catalog defaults" : "the fleet default"}.`).then(ok => ok && setEditing(undefined))}>
                  Reset to default
                </button>
                <button type="button" className="btn-ghost" onClick={() => setEditing(undefined)}>Cancel</button>
              </div>}
            </form>}
          </div>;
        })}
      </section>;
    })}
  </div>;
}
