import { useState, type FormEvent } from "react";
import AppShell from "../components/AppShell";
import { useAuth } from "../auth/AuthContext";
import { changeMyPassword, ApiError } from "../api";

export default function Account() {
  const { username, role } = useAuth();
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
    <AppShell active="status">
      <div className="page-inner" style={{ maxWidth: 420 }}>
        <div className="page-header-row">
          <h1 className="page-title">Account</h1>
        </div>
        <p style={{ color: "var(--mid)", fontSize: 13, margin: 0 }}>
          Signed in as <strong>{username}</strong> ({role})
        </p>

        <form className="field" style={{ display: "flex", flexDirection: "column", gap: 12 }} onSubmit={handleSubmit}>
          <label>
            New password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" minLength={8} required />
          </label>
          <label>
            Confirm new password
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" minLength={8} required />
          </label>
          {error && <div className="banner-error">{error}</div>}
          {done && (
            <div className="tag" style={{ color: "var(--status-ok)", background: "color-mix(in srgb, var(--status-ok) 12%, transparent)", width: "fit-content" }}>
              Password changed
            </div>
          )}
          <button type="submit" className="btn-primary" style={{ width: "fit-content" }} disabled={submitting}>
            {submitting ? "Saving…" : "Change password"}
          </button>
        </form>
      </div>
    </AppShell>
  );
}
