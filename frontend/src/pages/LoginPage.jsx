import { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../authContext";
import { useToast } from "../notifications";
import { ErrorState } from "../ui/primitives";

export default function LoginPage() {
  const { session, login } = useAuth();
  const { notify } = useToast();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (session) {
    const isBidder = session.role === "BIDDER";
    const home = isBidder ? "/portal" : "/dashboard";
    const from = location.state?.from?.pathname;
    // Only honor "return to where you came from" if that place actually
    // belongs to the portal this session's role gets. A stale `from` from
    // a *different* person's earlier session in the same tab (officer
    // signs out on an officer page, a bidder logs in next) must not send
    // the new session to a page meant for the other role -- see
    // RequireAuth's own comment in auth.jsx for how this showed up live.
    const fromMatchesRole = from && (isBidder ? from.startsWith("/portal") : !from.startsWith("/portal"));
    return <Navigate to={fromMatchesRole ? from : home} replace />;
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const next = await login(username, password);
      notify(`Signed in as ${next.displayName}.`, { kind: "success" });
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page" style={{ display: "grid", placeItems: "center", minHeight: "calc(100vh - 64px)" }}>
      <div className="card" style={{ width: "100%", maxWidth: 420 }}>
        <div className="card-body">
          <div className="page-eyebrow">Officer sign-in</div>
          <h1 className="section-title" style={{ marginBottom: 6 }}>SATYAPRAMĀṆ</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 20 }}>
            There is no self-signup. Every officer account is created by an administrator, and every action
            you take is recorded against your identity.
          </p>

          <ErrorState error={error} />

          <form className="form" onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="login-user">Username</label>
              <input id="login-user" value={username} autoComplete="username" required
                     onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="login-pass">Password</label>
              <input id="login-pass" type="password" value={password} autoComplete="current-password" required
                     onChange={(e) => setPassword(e.target.value)} />
            </div>
            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
        <div className="card-footer">
          <p className="text-xs text-muted">
            Sessions are signed and expire. Nothing you see in this application is simulated — where an
            authority cannot be reached, the answer is UNKNOWN with a stated reason.
          </p>
        </div>
      </div>
    </div>
  );
}
