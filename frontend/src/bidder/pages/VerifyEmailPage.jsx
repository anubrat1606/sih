import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { sendEmailVerification } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { ErrorState } from "../../ui/primitives";

// Requesting a verification email now really sends one when SMTP is
// configured (satyapramana_store/bidder_auth/email_sender.py) -- when it
// isn't, the backend answers plainly with delivered:false, shown below
// rather than a fabricated "check your inbox".
export default function VerifyEmailPage() {
  const navigate = useNavigate();
  const { bidder, isAuthenticated } = useBidderSession();
  const [status, setStatus] = useState("idle"); // idle | sending | sent | undelivered
  const [error, setError] = useState(null);
  const [detail, setDetail] = useState(null);

  async function resend() {
    setStatus("sending");
    setError(null);
    try {
      const outcome = await sendEmailVerification();
      if (outcome.alreadyVerified) {
        setStatus("sent");
      } else if (outcome.delivered) {
        setStatus("sent");
      } else {
        setStatus("undelivered");
        setDetail(outcome.detail);
      }
    } catch (err) {
      setStatus("idle");
      setError(err);
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="auth-page">
        <div className="card auth-card">
          <div className="card-body">
            <div className="page-eyebrow">Step 1 of 2</div>
            <h1 className="section-title" style={{ marginBottom: 4 }}>Verify your email</h1>
            <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
              Sign in first to request a verification email for your account.
            </p>
            <Link to="/bidder/login" className="btn btn-primary btn-block">Sign in</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="card-body">
          <div className="page-eyebrow">Step 1 of 2</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Verify your email</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
            {bidder.emailVerified
              ? <>Your email <strong className="mono">{bidder.email}</strong> is already verified.</>
              : <>We need to confirm <strong className="mono">{bidder.email}</strong> belongs to you before your account is fully active.</>}
          </p>

          <ErrorState error={error} />

          {!bidder.emailVerified && status !== "sent" && (
            <button type="button" className="btn btn-primary btn-block" onClick={resend} disabled={status === "sending"}>
              {status === "sending" ? "Sending…" : "Send verification email"}
            </button>
          )}

          {status === "sent" && (
            <div className="unavailable-note" role="status">
              <span className="unavailable-note-glyph" aria-hidden="true">✓</span>
              <div>Sent. Open the link in that email on this device to finish verifying.</div>
            </div>
          )}

          {status === "undelivered" && (
            <div className="unavailable-note" role="status">
              <span className="unavailable-note-glyph" aria-hidden="true">⚙</span>
              <div>
                A verification link was generated for real, but this deployment has no email provider
                configured to send it.
                <div className="text-xs text-muted mono" style={{ marginTop: 6 }}>{detail}</div>
              </div>
            </div>
          )}

          <p className="text-xs text-muted" style={{ marginTop: 20 }}>
            <button type="button" className="link-button" onClick={() => navigate("/bidder/verify-mobile")}>
              Continue to mobile verification
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
