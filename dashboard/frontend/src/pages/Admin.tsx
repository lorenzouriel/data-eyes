import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, Navigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { useAuth } from "../auth/AuthContext";
import {
  getInstances,
  createInstance,
  updateInstance,
  deleteInstance,
  getUsers,
  createUser,
  deleteUser,
  ApiError,
} from "../api";
import type { AppUser, InstanceSummary, Role } from "../types";

const ADMIN_TABS = [
  { key: "users", label: "Users" },
  { key: "instances", label: "Monitored instances" },
];

function InstanceForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: { name: string; label: string; environment: string };
  submitLabel: string;
  onSubmit: (values: { name: string; label: string; environment: string; connectionString: string }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [label, setLabel] = useState(initial?.label ?? "");
  const [environment, setEnvironment] = useState(initial?.environment ?? "");
  const [connectionString, setConnectionString] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({ name, label, environment, connectionString });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save instance");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="field panel-card" style={{ padding: 16, marginBottom: 16, display: "flex", flexDirection: "column", gap: 12 }} onSubmit={handleSubmit}>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <label style={{ flex: 1, minWidth: 160 }}>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={!!initial} required />
        </label>
        <label style={{ flex: 1, minWidth: 160 }}>
          Label
          <input value={label} onChange={(e) => setLabel(e.target.value)} required />
        </label>
        <label style={{ flex: 1, minWidth: 160 }}>
          Environment
          <input value={environment} onChange={(e) => setEnvironment(e.target.value)} placeholder="production" />
        </label>
      </div>
      <label>
        {initial ? "New connection string (leave blank to keep the current one)" : "SQL Server connection string"}
        <input
          className="mono"
          value={connectionString}
          onChange={(e) => setConnectionString(e.target.value)}
          placeholder="Driver={ODBC Driver 17 for SQL Server};Server=...;Database=...;UID=...;PWD=..."
          required={!initial}
        />
      </label>
      {error && <div className="banner-error">{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function InstancesAdmin() {
  const [instances, setInstances] = useState<InstanceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const load = useCallback(() => {
    getInstances()
      .then(setInstances)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load instances"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        {!adding && (
          <button className="btn-primary" onClick={() => setAdding(true)}>
            Register instance
          </button>
        )}
      </div>

      {error && <div className="banner-error">{error}</div>}

      {adding && (
        <InstanceForm
          submitLabel="Add Instance"
          onCancel={() => setAdding(false)}
          onSubmit={async (values) => {
            await createInstance({
              name: values.name,
              label: values.label,
              environment: values.environment || undefined,
              connection_string: values.connectionString,
            });
            setAdding(false);
            load();
          }}
        />
      )}

      {!instances && !error && <div className="page-loading">Loading…</div>}
      {instances && instances.length === 0 && !adding && <div className="empty-state">No instances registered yet.</div>}

      {instances && instances.length > 0 && (
        <div className="panel-card" style={{ overflowX: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(190px, 1.5fr) 120px 1fr", padding: "9px 18px", borderBottom: "1px solid var(--line)" }}>
            <span className="th-label">INSTANCE</span>
            <span className="th-label">ENVIRONMENT</span>
            <span />
          </div>
          {instances.map((instance) =>
            editing === instance.name ? (
              <div key={instance.name} style={{ padding: "12px 18px" }}>
                <InstanceForm
                  initial={{ name: instance.name, label: instance.label, environment: instance.environment ?? "" }}
                  submitLabel="Save"
                  onCancel={() => setEditing(null)}
                  onSubmit={async (values) => {
                    await updateInstance(instance.name, {
                      label: values.label,
                      environment: values.environment || undefined,
                      clear_environment: !values.environment,
                      connection_string: values.connectionString || undefined,
                    });
                    setEditing(null);
                    load();
                  }}
                />
              </div>
            ) : (
              <div
                key={instance.name}
                style={{ display: "grid", gridTemplateColumns: "minmax(190px, 1.5fr) 120px 1fr", alignItems: "center", padding: "11px 18px", borderBottom: "1px solid var(--line2)" }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span style={{ font: "500 12.5px 'Space Grotesk', sans-serif" }}>{instance.label}</span>
                  <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>{instance.name}</span>
                </div>
                <span className="mono" style={{ fontSize: 11.5, color: "var(--mid)" }}>{instance.environment ?? "—"}</span>
                <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                  <button className="btn-ghost" onClick={() => setEditing(instance.name)}>
                    Edit
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={async () => {
                      if (!confirm(`Remove instance "${instance.name}"?`)) return;
                      try {
                        await deleteInstance(instance.name);
                        load();
                      } catch (err) {
                        setError(err instanceof ApiError ? err.message : "Failed to delete instance");
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ),
          )}
        </div>
      )}
    </div>
  );
}

function UsersAdmin() {
  const { username: currentUsername } = useAuth();
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(() => {
    getUsers()
      .then(setUsers)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load users"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await createUser({ username, password, role });
      setUsername("");
      setPassword("");
      setRole("member");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add user");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <form className="field panel-card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }} onSubmit={handleSubmit}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <label style={{ flex: 1, minWidth: 160 }}>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" required />
          </label>
          <label style={{ flex: 1, minWidth: 160 }}>
            Initial password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" minLength={8} required />
          </label>
          <label style={{ flex: 1, minWidth: 160 }}>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </label>
        </div>
        {error && <div className="banner-error">{error}</div>}
        <button type="submit" className="btn-primary" style={{ width: "fit-content" }} disabled={submitting}>
          {submitting ? "Adding…" : "Invite user"}
        </button>
      </form>

      {!users && !error && <div className="page-loading">Loading…</div>}
      {users && users.length > 0 && (
        <div className="panel-card" style={{ overflowX: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1.8fr) 108px 150px 96px", padding: "9px 18px", borderBottom: "1px solid var(--line)" }}>
            <span className="th-label">USER</span>
            <span className="th-label">ACCESS</span>
            <span className="th-label">CREATED</span>
            <span />
          </div>
          {users.map((user) => (
            <div key={user.username} style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1.8fr) 108px 150px 96px", alignItems: "center", padding: "11px 18px", borderBottom: "1px solid var(--line2)" }}>
              <span style={{ font: "500 12.5px 'Space Grotesk', sans-serif" }}>{user.username}</span>
              <span className="tag" style={{ justifySelf: "start", color: user.role === "admin" ? "var(--accent)" : "var(--mid)", background: user.role === "admin" ? "var(--accentSoft)" : "var(--soft)" }}>
                {user.role === "admin" ? "Admin" : "User"}
              </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>{new Date(user.created_at).toLocaleDateString()}</span>
              {user.username !== currentUsername && (
                <button
                  className="btn-ghost"
                  style={{ justifySelf: "end" }}
                  onClick={async () => {
                    if (!confirm(`Remove user "${user.username}"?`)) return;
                    try {
                      await deleteUser(user.username);
                      load();
                    } catch (err) {
                      setError(err instanceof ApiError ? err.message : "Failed to delete user");
                    }
                  }}
                >
                  Delete
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.6, color: "var(--muted)", maxWidth: 680 }}>
        One shared team: every user sees and manages the same instance registry. <span style={{ color: "var(--text)" }}>Admin</span> additionally sees this panel and
        manages users; <span style={{ color: "var(--text)" }}>User</span> sees Status and drills into any instance.
      </p>
    </div>
  );
}

export default function Admin() {
  const { role } = useAuth();
  const navigate = useNavigate();
  const { tab } = useParams();
  const activeTab = tab && ADMIN_TABS.some((t) => t.key === tab) ? tab : "users";

  if (role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return (
    <AppShell active="status">
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100%" }}>
        <div style={{ flex: "none", background: "var(--panel)", borderBottom: "1px solid var(--line)", padding: "18px 24px 0" }}>
          <div style={{ maxWidth: 1500, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <h1 className="page-title">Administration</h1>
              <p className="page-subtitle">Who can see what, and which SQL Server instances Data Eyes collects from.</p>
            </div>
            <div style={{ display: "flex", gap: 4, overflowX: "auto" }}>
              {ADMIN_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => navigate(`/admin/${t.key}`)}
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
          <div style={{ maxWidth: 1500, margin: "0 auto" }}>{activeTab === "users" ? <UsersAdmin /> : <InstancesAdmin />}</div>
        </div>
      </div>
    </AppShell>
  );
}
