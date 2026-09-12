import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "../bidderApi";
import { isPasswordValid, PasswordStrengthMeter } from "../components/FormControls";
import { ErrorState } from "../../ui/primitives";

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  const passwordValid = isPasswordValid(password);
  const confirmValid = confirm !== "" && confirm === password;
  const canSubmit = Boolean(token) && passwordValid && confirmValid;

  async function onSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="card-body">
          <div className="page-eyebrow">Bidder account</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Set a new password</h1>

          {!token ? (
            <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
              This page needs a reset link — request one from <Link to="/bidder/forgot-password">Reset your password</Link>.
            </p>
          ) : done ? (
            <>
              <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>Your password has been updated.</p>
              <button type="button" className="btn btn-primary btn-block" onClick={() => navigate("/bidder/login")}>
                Sign in
              </button>
            </>
          ) : (
            <>
              <ErrorState error={error} />
              <form className="form" onSubmit={onSubmit} noValidate>
                <div className="field">
                  <label htmlFor="rp-pass">New password</label>
                  <input id="rp-pass" type="password" autoComplete="new-password" value={password}
                         onChange={(e) => setPassword(e.target.value)} required />
                  <PasswordStrengthMeter password={password} />
                </div>
                <div className="field">
                  <label htmlFor="rp-confirm">Confirm new password</label>
                  <input id="rp-confirm" type="password" autoComplete="new-password" value={confirm}
                         onChange={(e) => setConfirm(e.target.value)} required
                         aria-invalid={confirm !== "" && !confirmValid} />
                  {confirm !== "" && !confirmValid && (
                    <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Passwords do not match.</span>
                  )}
                </div>
                <button type="submit" className="btn btn-primary btn-block" disabled={submitting || !canSubmit}>
                  {submitting ? "Updating…" : "Update password"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
