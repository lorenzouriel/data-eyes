import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getInstance, ApiError } from "../api";
import type { InstanceDetail as InstanceDetailType } from "../types";

export default function InstanceDetail() {
  const { instanceName = "" } = useParams();
  const [detail, setDetail] = useState<InstanceDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    getInstance(instanceName)
      .then(setDetail)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load instance"));
  }, [instanceName]);

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Data Eyes</span>
        </div>
        <Link className="btn-ghost" to="/">
          ← Fleet
        </Link>
      </header>

      <main className="main-content">
        <div className="main-heading">
          <h1>{detail?.label ?? instanceName}</h1>
        </div>

        {error && <div className="banner-error">{error}</div>}
        {!detail && !error && <div className="page-loading">Loading databases…</div>}

        {detail && (
          <div className="database-list">
            {detail.databases.map((db) => (
              <Link
                key={db.name}
                className="database-row"
                to={`/instances/${encodeURIComponent(instanceName)}/db/${encodeURIComponent(db.name)}/wait-time`}
              >
                <span className="database-name">{db.name}</span>
                <span className="database-state">{db.state}</span>
              </Link>
            ))}
            {detail.databases.length === 0 && <div className="empty-state">No databases found.</div>}
          </div>
        )}
      </main>
    </div>
  );
}
