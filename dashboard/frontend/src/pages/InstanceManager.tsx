import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getInstances, createInstance, updateInstance, deleteInstance, ApiError } from "../api";
import type { InstanceSummary } from "../types";
import Logo from "../components/Logo";

// The connection string is write-only from the frontend's perspective — the
// backend never returns it (see app/routers/instances.py's InstanceSummary),
// so editing one always means typing a fresh value, never pre-filling a
// decrypted secret into a form field.
function InstanceForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: { name: string; label: string; environment: string };
  submitLabel: string;
  onSubmit: (values: { name: string; label: string; environment: string; connectionString: string }) => Promise<void>;
  onCancel?: () => void;
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
    <form className="manager-form" onSubmit={handleSubmit}>
      <div className="manager-form-row">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={!!initial} required />
        </label>
        <label>
          Label
          <input value={label} onChange={(e) => setLabel(e.target.value)} required />
        </label>
        <label>
          Environment
          <input value={environment} onChange={(e) => setEnvironment(e.target.value)} placeholder="production" />
        </label>
      </div>
      <label>
        {initial ? "New connection string (leave blank to keep the current one)" : "SQL Server connection string"}
        <input
          className="manager-form-connstr"
          value={connectionString}
          onChange={(e) => setConnectionString(e.target.value)}
          placeholder="Driver={ODBC Driver 17 for SQL Server};Server=...;Database=...;UID=...;PWD=..."
          required={!initial}
        />
      </label>
      {error && <div className="banner-error">{error}</div>}
      <div className="manager-form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

export default function InstanceManager() {
  const { username, logout } = useAuth();
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
    <div className="page">
      <header className="topbar">
        <div className="topbar-brand">
          <Logo className="brand-mark" />
          <span className="brand-name">Data Eyes</span>
        </div>
        <div className="topbar-right">
          <Link className="btn-ghost" to="/">
            ← Fleet
          </Link>
          <span className="topbar-user">{username}</span>
          <button className="btn-ghost" onClick={() => logout()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="main-heading">
          <h1>Manage Instances</h1>
          {!adding && (
            <button className="btn-primary" onClick={() => setAdding(true)}>
              Add Instance
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

        {instances && instances.length === 0 && !adding && (
          <div className="empty-state">No instances registered yet — click "Add Instance" to register one.</div>
        )}

        {instances && instances.length > 0 && (
          <div className="table-scroll">
            <table className="data-table manager-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Label</th>
                  <th>Environment</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {instances.map((instance) =>
                  editing === instance.name ? (
                    <tr key={instance.name}>
                      <td colSpan={4}>
                        <InstanceForm
                          initial={{
                            name: instance.name,
                            label: instance.label,
                            environment: instance.environment ?? "",
                          }}
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
                      </td>
                    </tr>
                  ) : (
                    <tr key={instance.name}>
                      <td>{instance.name}</td>
                      <td>{instance.label}</td>
                      <td>{instance.environment ?? "—"}</td>
                      <td className="manager-table-actions">
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
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
