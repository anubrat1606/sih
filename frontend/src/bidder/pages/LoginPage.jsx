import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BackendNotImplementedError, continueWithGoogle, login } from "../bidderApi";
import { isValidEmail } from "../components/FormControls";
import { BackendPendingNotice } from "../components/BackendPendingNotice";

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [pending, setPending] = useState(null);

  const emailValid = email === "" ? null : isValidEmail(email);
  const canSubmit = emailValid && password.length > 0;

  async function onSubmit(e) {
    e.preventDefault();
    setTouched(true);
    if (!canSubmit) return;
    setSubmitting(true);
    setPending(null);
    try {
      await login({ email: email.trim(), password });
      navigate("/bidder/dashboard");
    } catch (err) {
      setPending(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function onGoogle() {
    setPending(null);
    try {
      await continueWithGoogle();
      navigate("/bidder/dashboard");
    } catch (err) {
      setPending(err);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="card-body">
          <div className="page-eyebrow">Bidder account</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Sign in</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 20 }}>
            Sign in to track your bids and view results.
          </p>

          <button type="button" className="btn-google" onClick={onGoogle}>
            <span aria-hidden="true">G</span> Continue with Google
          </button>
          <div className="auth-divider">or sign in with email</div>

          <form className="form" onSubmit={onSubmit} noValidate>
            <div className="field">
              <label htmlFor="li-email">Email address</label>
              <input id="li-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                     onBlur={() => setTouched(true)} required aria-invalid={touched && emailValid === false} />
              {touched && emailValid === false && (
                <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Enter a valid email address.</span>
              )}
            </div>
            <div className="field">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <label htmlFor="li-pass">Password</label>
                <Link to="/bidder/forgot-password" className="text-xs">Forgot password?</Link>
              </div>
              <input id="li-pass" type="password" autoComplete="current-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} required />
            </div>

            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {pending instanceof BackendNotImplementedError && (
            <div style={{ marginTop: 16 }}>
              <BackendPendingNotice endpoint={pending.requiredEndpoint}>
                {pending.message} Sign-in cannot be completed until this exists — no session has been created.
              </BackendPendingNotice>
            </div>
          )}

          <p className="text-sm text-secondary" style={{ marginTop: 20 }}>
            New here? <Link to="/bidder/signup">Create an account</Link>
          </p>
          <p className="text-xs text-muted" style={{ marginTop: 8 }}>
            Didn't get a verification link? <Link to="/bidder/verify-email">Resend it</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
