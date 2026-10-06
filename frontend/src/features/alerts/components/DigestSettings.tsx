import { useEffect, useState } from "react";
import type { NotificationChannel } from "../../notifications/types";
import type { DigestSetting } from "../types";

interface Props {
  digest: DigestSetting;
  channels: NotificationChannel[];
  busy: boolean;
  save: (setting: DigestSetting) => Promise<boolean>;
}

export default function DigestSettings({ digest, channels, busy, save }: Props) {
  const [draft, setDraft] = useState(digest);
  useEffect(() => setDraft(digest), [digest]);
  const toggleChannel = (id: number, on: boolean) =>
    setDraft({ ...draft, channel_ids: on ? [...draft.channel_ids, id] : draft.channel_ids.filter(c => c !== id) });

  return <form className="panel-card alerts-card alerts-digest field" onSubmit={e => {
    e.preventDefault();
    void save({ enabled: draft.enabled, hour_utc: draft.hour_utc, channel_ids: draft.channel_ids });
  }}>
    <div>
      <strong>Daily DB checklist</strong>
      <p className="alerts-hint">Once a day, one summary per channel: open alerts per instance, events from the last 24 hours, and
        checks that could not run. It is sent directly to the channels below and ignores notification rules.</p>
    </div>
    <label className="alerts-inline"><input type="checkbox" checked={draft.enabled} onChange={e => setDraft({ ...draft, enabled: e.target.checked })} />
      Send the daily checklist</label>
    <label style={{ maxWidth: 260 }}>Send at or after (UTC hour, 0–23)
      <input type="number" min={0} max={23} required value={draft.hour_utc} onChange={e => setDraft({ ...draft, hour_utc: Number(e.target.value) })} />
    </label>
    <fieldset className="alerts-fieldset">
      <legend>Channels</legend>
      {channels.map(c => <label key={c.id} className="alerts-inline">
        <input type="checkbox" checked={draft.channel_ids.includes(c.id)} onChange={e => toggleChannel(c.id, e.target.checked)} />
        {c.name} <span className="alerts-muted">{c.type}{c.enabled ? "" : " · disabled"}</span>
      </label>)}
      {!channels.length && <span className="alerts-muted">No channels yet. Add one on the Notifications page.</span>}
    </fieldset>
    <div className="alerts-editor-actions">
      <button type="submit" className="btn-primary" disabled={busy || (draft.enabled && !draft.channel_ids.length)}>Save checklist</button>
      {digest.last_sent_on && <span className="alerts-muted">Last sent {digest.last_sent_on}</span>}
    </div>
  </form>;
}
