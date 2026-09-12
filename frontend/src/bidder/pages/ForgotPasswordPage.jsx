import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../bidderApi";
import { isValidEmail } from "../components/FormControls";
import { ErrorState } from "../../ui/primitives";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);

  const emailValid = email !== "" && isValidEmail(email);

  async function onSubmit(e) {
    e.preventDefault();
    if (!emailValid) return;
    setSubmitting(true);
    setError(null);
    try {
      await forgotPassword(email.trim());
      // The backend deliberately returns the same response whether or not
      // an account exists for this email -- shown as-is, not replaced with
      // an even vaguer message, since it's already the honest, safe answer.
      setSent(true);
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
          <h1 className="section-title" style={{ marginBottom: 4 }}>Reset your password</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
            Enter the email address on your account and we'll send a reset link.
          </p>

          <ErrorState error={error} />

          {sent ? (
            <div className="unavailable-note" role="status">
              <span className="unavailable-note-glyph" aria-hidden="true">✓</span>
              <div>If an account exists for that email, a reset link has been sent to it.</div>
            </div>
          ) : (
            <form className="form" onSubmit={onSubmit} noValidate>
              <div className="field">
                <label htmlFor="fp-email">Email address</label>
                <input id="fp-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <button type="submit" className="btn btn-primary btn-block" disabled={submitting || !emailValid}>
                {submitting ? "Sending…" : "Send reset link"}
              </button>
            </form>
          )}

          <p className="text-sm text-secondary" style={{ marginTop: 20 }}>
            <Link to="/bidder/login">Back to sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
