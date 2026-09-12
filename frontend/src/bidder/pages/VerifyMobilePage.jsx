import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BackendNotImplementedError, confirmMobileOtp, sendMobileOtp } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { formatIndianMobile, formatCountdown, OtpInput, useCountdown } from "../components/FormControls";
import { BackendPendingNotice } from "../components/BackendPendingNotice";

const RESEND_COOLDOWN = 30;

export default function VerifyMobilePage() {
  const navigate = useNavigate();
  const { profile } = useBidderSession();
  const [otp, setOtp] = useState("");
  const [status, setStatus] = useState("idle"); // idle | sent | verifying | error
  const [pending, setPending] = useState(null);
  const [cooldownSeed, setCooldownSeed] = useState(0);
  const cooldown = useCountdown(cooldownSeed);

  async function sendCode() {
    setPending(null);
    try {
      await sendMobileOtp(profile?.mobile);
      setStatus("sent");
      setCooldownSeed(RESEND_COOLDOWN);
    } catch (err) {
      setStatus("error");
      setPending(err);
    }
  }

  async function verify(e) {
    e.preventDefault();
    setStatus("verifying");
    setPending(null);
    try {
      await confirmMobileOtp(profile?.mobile, otp);
      navigate("/bidder/dashboard");
    } catch (err) {
      setStatus("error");
      setPending(err);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="card-body">
          <div className="page-eyebrow">Step 2 of 2</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Verify your mobile number</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
            {profile?.mobile
              ? <>Enter the 6-digit code sent to <strong className="mono">{formatIndianMobile(profile.mobile)}</strong>.</>
              : "Enter the 6-digit code sent to your mobile number."}
          </p>

          {status === "idle" ? (
            <button type="button" className="btn btn-primary btn-block" onClick={sendCode}>
              Send verification code
            </button>
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

          {pending instanceof BackendNotImplementedError && (
            <div style={{ marginTop: 16 }}>
              <BackendPendingNotice endpoint={pending.requiredEndpoint}>
                {pending.message} No code has actually been sent or checked — this screen will never
                hardcode a successful verification.
              </BackendPendingNotice>
            </div>
          )}

          <p className="text-xs text-muted" style={{ marginTop: 20 }}>
            Wrong number? <Link to="/bidder/signup">Update your details</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
