import { useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../authContext";
import { AshokaChakra, Icon } from "../landing/Emblems";
import { useToast } from "../notifications";
import { ErrorState } from "../ui/primitives";
import "./login.css";

const ASSURANCES = [
  { icon: "shield", text: "PAN, GST and CIN are checked with the issuing authority, live." },
  { icon: "chain", text: "Every action you take is an event on an append-only, hash-chained log." },
  { icon: "ban", text: "Nothing here is simulated. Where an authority can't be reached, the answer is UNKNOWN with a reason." },
];

export default function LoginPage() {
  const { session, login } = useAuth();
  const { notify } = useToast();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="login">
      <div className="lp-ribbon" aria-hidden="true"><span /><span /><span /></div>
      <div className="login-grid">
        <aside className="login-brand">
          <AshokaChakra className="login-chakra" size={560} />
          <Link to="/" className="login-back"><Icon name="arrow" size={16} className="login-back-icon" /> Back to overview</Link>
          <div className="login-brand-body">
            <p className="login-eyebrow">Tender compliance verification</p>
            <h1 className="login-title">
              <span lang="hi" className="login-devanagari">सत्यप्रमाण</span>
              <span className="login-latin">Satyapramāṇ</span>
            </h1>
            <ul className="login-assurances">
              {ASSURANCES.map((a) => (
                <li key={a.icon}><span className="login-assurance-icon"><Icon name={a.icon} size={18} /></span><span>{a.text}</span></li>
              ))}
            </ul>
          </div>
          <p className="login-brand-foot">Prototype · Smart India Hackathon 2026 · SIH26100</p>
        </aside>

        <section className="login-panel" aria-labelledby="login-heading">
          <div className="login-card">
            <p className="page-eyebrow">Sign in</p>
            <h2 id="login-heading" className="login-heading">Officers and bidders</h2>
            <p className="login-lede">
              Accounts are provisioned by an administrator — there is no self-signup. Your role decides where you land:
              Mission Control for officers, the portal for bidders.
            </p>

            <ErrorState error={error} />

            <form className="form login-form" onSubmit={onSubmit}>
              <div className="field">
                <label htmlFor="login-user">Username</label>
                <input id="login-user" value={username} autoComplete="username" required autoFocus
                       onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="login-pass">Password</label>
                <div className="login-password">
                  <input id="login-pass" type={showPassword ? "text" : "password"} value={password}
                         autoComplete="current-password" required onChange={(e) => setPassword(e.target.value)} />
                  <button type="button" className="login-password-toggle" onClick={() => setShowPassword((v) => !v)}
                          aria-pressed={showPassword} aria-label={showPassword ? "Hide password" : "Show password"}>
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
              <button type="submit" className="btn btn-primary btn-block login-submit" disabled={submitting}>
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </form>

            <p className="login-foot text-xs text-muted">
              Sessions are signed and expire. Every action is recorded against your identity — a decision is never
              attributed to a client-supplied name.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
