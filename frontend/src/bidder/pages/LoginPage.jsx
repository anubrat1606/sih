import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BackendNotImplementedError, continueWithGoogle, login } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { isValidEmail } from "../components/FormControls";
import { BackendPendingNotice } from "../components/BackendPendingNotice";
import { ErrorState } from "../../ui/primitives";

export default function LoginPage() {
  const navigate = useNavigate();
  const { setSession } = useBidderSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [googlePending, setGooglePending] = useState(null);

  const emailValid = email === "" ? null : isValidEmail(email);
  const canSubmit = emailValid && password.length > 0;

  async function onSubmit(e) {
    e.preventDefault();
    setTouched(true);
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const { token, bidder } = await login({ email: email.trim(), password });
      setSession({ token, bidder });
      navigate("/bidder/dashboard");
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function onGoogle() {
    setGooglePending(null);
    try {
      // No Google ID token is available here -- continueWithGoogle() only
      // ever gets one from Google Identity Services' own SDK, which isn't
      // loaded because GOOGLE_CLIENT_ID isn't configured (see bidderApi.js).
      // Calling it anyway surfaces the real, precise reason rather than
      // this button silently doing nothing.
      const { token, bidder } = await continueWithGoogle(undefined);
      setSession({ token, bidder });
      navigate("/bidder/dashboard");
    } catch (err) {
      setGooglePending(err);
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
          {googlePending instanceof BackendNotImplementedError && (
            <div style={{ marginTop: 12 }}>
              <BackendPendingNotice endpoint={googlePending.requiredEndpoint}>{googlePending.message}</BackendPendingNotice>
            </div>
          )}
          <div className="auth-divider">or sign in with email</div>

          <ErrorState error={error} />

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
