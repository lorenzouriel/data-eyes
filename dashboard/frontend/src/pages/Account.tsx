import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { changeMyPassword, ApiError } from "../api";
import Logo from "../components/Logo";

export default function Account() {
  const { username, role, logout } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setSubmitting(true);
    try {
      await changeMyPassword(password);
      setPassword("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to change password");
    } finally {
      setSubmitting(false);
    }
  };

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
          <h1>Account</h1>
        </div>

        <p className="account-meta">
          Signed in as <strong>{username}</strong> ({role})
        </p>

        <form className="manager-form manager-form--narrow" onSubmit={handleSubmit}>
          <label>
            New password
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
            Confirm new password
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>
          {error && <div className="banner-error">{error}</div>}
          {done && <div className="account-success">Password changed.</div>}
          <div className="manager-form-actions">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? "Saving…" : "Change Password"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
