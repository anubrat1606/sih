import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BackendNotImplementedError, sendEmailVerification } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { BackendPendingNotice } from "../components/BackendPendingNotice";

// Real states this screen can honestly be in. Nothing here ever shows
// "verified" unless a real backend confirms it -- today that confirmation
// can never arrive, so this screen can only ever reach "pending"/"error",
// never "success".
export default function VerifyEmailPage() {
  const navigate = useNavigate();
  const { profile } = useBidderSession();
  const [status, setStatus] = useState("idle"); // idle | sending | sent | error
  const [pending, setPending] = useState(null);

  async function resend() {
    setStatus("sending");
    setPending(null);
    try {
      await sendEmailVerification(profile?.email);
      setStatus("sent");
    } catch (err) {
      setStatus("error");
      setPending(err);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="card-body">
          <div className="page-eyebrow">Step 1 of 2</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Verify your email</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
            {profile?.email
              ? <>We need to confirm <strong className="mono">{profile.email}</strong> belongs to you before your account is active.</>
              : "We need to confirm your email address belongs to you before your account is active."}
          </p>

          {status !== "sent" && (
            <button type="button" className="btn btn-primary btn-block" onClick={resend} disabled={status === "sending"}>
              {status === "sending" ? "Sending…" : "Send verification email"}
            </button>
          )}

          {status === "sent" && (
            <div className="unavailable-note" role="status">
              <span className="unavailable-note-glyph" aria-hidden="true">✓</span>
              <div>Requested. This will only take effect once the backend can actually send and confirm emails.</div>
            </div>
          )}

          {pending instanceof BackendNotImplementedError && (
            <div style={{ marginTop: 16 }}>
              <BackendPendingNotice endpoint={pending.requiredEndpoint}>
                {pending.message} Your account stays unverified until this is built — this page will never show
                a fake "email verified" state.
              </BackendPendingNotice>
            </div>
          )}

          <p className="text-sm text-secondary" style={{ marginTop: 20 }}>
            Wrong email? <Link to="/bidder/signup">Update your details</Link>
          </p>
          <p className="text-xs text-muted" style={{ marginTop: 8 }}>
            Already verified? <button type="button" className="link-button" onClick={() => navigate("/bidder/verify-mobile")}>
              Continue to mobile verification
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
