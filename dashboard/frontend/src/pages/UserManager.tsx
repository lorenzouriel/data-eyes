import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getUsers, createUser, deleteUser, ApiError } from "../api";
import type { AppUser, Role } from "../types";
import Logo from "../components/Logo";

function AddUserForm({ onAdded }: { onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await createUser({ username, password, role });
      setUsername("");
      setPassword("");
      setRole("member");
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add user");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="manager-form" onSubmit={handleSubmit}>
      <div className="manager-form-row">
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" required />
        </label>
        <label>
          Initial password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
        </label>
      </div>
      {error && <div className="banner-error">{error}</div>}
      <div className="manager-form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Adding…" : "Add User"}
        </button>
      </div>
    </form>
  );
}

export default function UserManager() {
  const { username: currentUsername, role, logout } = useAuth();
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getUsers()
      .then(setUsers)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load users"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // This page is admin-only — role is already known by the time a logged-in
  // user reaches here (AuthContext resolves it on mount), so a non-admin
  // bounces straight back to the fleet rather than seeing a 403 from the API.
  if (role !== "admin") {
    return <Navigate to="/" replace />;
  }

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
          <span className="topbar-user">{currentUsername}</span>
          <button className="btn-ghost" onClick={() => logout()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="main-heading">
          <h1>Manage Users</h1>
        </div>

        {error && <div className="banner-error">{error}</div>}

        <AddUserForm onAdded={load} />

        {!users && !error && <div className="page-loading">Loading…</div>}

        {users && users.length > 0 && (
          <div className="table-scroll">
            <table className="data-table manager-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.username}>
                    <td>{user.username}</td>
                    <td>{user.role}</td>
                    <td>{new Date(user.created_at).toLocaleString()}</td>
                    <td className="manager-table-actions">
                      {user.username !== currentUsername && (
                        <button
                          className="btn-ghost"
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
