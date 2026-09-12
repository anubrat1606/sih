import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { confirmMobileOtp, sendMobileOtp } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { formatIndianMobile, formatCountdown, OtpInput, useCountdown } from "../components/FormControls";
import { ErrorState } from "../../ui/primitives";

const RESEND_COOLDOWN = 30;

// The OTP itself is real (satyapramana_store/bidder_auth -- generated with
// `secrets`, hashed, rate-limited, expires in 10 minutes). Only its
// delivery to an actual phone depends on an SMS provider being configured,
// which this deployment doesn't have -- see sms_sender.py. When
// delivered:false comes back, this screen says so plainly instead of
// pretending a text was sent.
export default function VerifyMobilePage() {
  const navigate = useNavigate();
  const { bidder, updateBidder, isAuthenticated } = useBidderSession();
  const [otp, setOtp] = useState("");
  const [status, setStatus] = useState("idle"); // idle | sent | undelivered | verifying
  const [error, setError] = useState(null);
  const [detail, setDetail] = useState(null);
  const [cooldownSeed, setCooldownSeed] = useState(0);
  const cooldown = useCountdown(cooldownSeed);

  async function sendCode() {
    setError(null);
    try {
      const outcome = await sendMobileOtp();
      if (outcome.alreadyVerified) {
        setStatus("sent");
      } else if (outcome.delivered) {
        setStatus("sent");
      } else {
        setStatus("undelivered");
        setDetail(outcome.detail);
      }
      setCooldownSeed(RESEND_COOLDOWN);
    } catch (err) {
      setError(err);
    }
  }

  async function verify(e) {
    e.preventDefault();
    setStatus("verifying");
    setError(null);
    try {
      await confirmMobileOtp(otp);
      updateBidder({ mobileVerified: true });
      navigate("/bidder/dashboard");
    } catch (err) {
      setStatus("sent");
      setError(err);
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="auth-page">
        <div className="card auth-card">
          <div className="card-body">
            <div className="page-eyebrow">Step 2 of 2</div>
            <h1 className="section-title" style={{ marginBottom: 4 }}>Verify your mobile number</h1>
            <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>Sign in first to verify your mobile number.</p>
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
          <div className="page-eyebrow">Step 2 of 2</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Verify your mobile number</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
            {bidder.mobileVerified
              ? <>Your mobile number <strong className="mono">{formatIndianMobile(bidder.mobile)}</strong> is already verified.</>
              : <>Enter the 6-digit code sent to <strong className="mono">{formatIndianMobile(bidder.mobile)}</strong>.</>}
          </p>

          <ErrorState error={error} />

          {bidder.mobileVerified ? null : status === "idle" ? (
            <button type="button" className="btn btn-primary btn-block" onClick={sendCode}>
              Send verification code
            </button>
          ) : status === "undelivered" ? (
            <div className="unavailable-note" role="status">
              <span className="unavailable-note-glyph" aria-hidden="true">⚙</span>
              <div>
                A verification code was generated for real, but this deployment has no SMS provider
                configured to text it to a phone.
                <div className="text-xs text-muted mono" style={{ marginTop: 6 }}>{detail}</div>
              </div>
            </div>
          ) : (
            <form onSubmit={verify}>
              <OtpInput length={6} value={otp} onChange={setOtp} disabled={status === "verifying"} />
              <button type="submit" className="btn btn-primary btn-block" style={{ marginTop: 16 }}
                      disabled={otp.length !== 6 || status === "verifying"}>
                {status === "verifying" ? "Verifying…" : "Verify code"}
              </button>
              <div className="row" style={{ justifyContent: "center", marginTop: 12 }}>
                {cooldown > 0 ? (
                  <span className="text-xs text-muted">Resend code in {formatCountdown(cooldown)}</span>
                ) : (
                  <button type="button" className="link-button text-xs" onClick={sendCode}>Resend code</button>
                )}
              </div>
            </form>
          )}

          <p className="text-xs text-muted" style={{ marginTop: 20 }}>
            <button type="button" className="link-button" onClick={() => navigate("/bidder/dashboard")}>
              Skip for now
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
