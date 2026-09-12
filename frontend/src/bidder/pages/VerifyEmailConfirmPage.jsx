import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { confirmEmailVerification } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";

// The landing page the link in a verification email actually points to
// (see app.py's _send_bidder_email_verification -- {frontend origin}
// /bidder/verify-email/confirm?token=...). Distinct from VerifyEmailPage,
// which is the "request a link" screen shown before this one.
export default function VerifyEmailConfirmPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { updateBidder, isAuthenticated } = useBidderSession();
  const [state, setState] = useState("checking"); // checking | success | failed

  useEffect(() => {
    if (!token) { setState("failed"); return; }
    let cancelled = false;
    confirmEmailVerification(token)
      .then((account) => {
        if (cancelled) return;
        if (isAuthenticated) updateBidder({ emailVerified: account.emailVerified });
        setState("success");
      })
      .catch(() => { if (!cancelled) setState("failed"); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="card-body">
          <div className="page-eyebrow">Email verification</div>
          {state === "checking" && <p className="text-sm text-secondary">Checking your verification link…</p>}
          {state === "success" && (
            <>
              <h1 className="section-title" style={{ marginBottom: 4 }}>Email verified</h1>
              <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
                Your email address is confirmed.
              </p>
              <Link to={isAuthenticated ? "/bidder/dashboard" : "/bidder/login"} className="btn btn-primary btn-block">
                {isAuthenticated ? "Go to dashboard" : "Sign in"}
              </Link>
            </>
          )}
          {state === "failed" && (
            <>
              <h1 className="section-title" style={{ marginBottom: 4 }}>Link invalid or expired</h1>
              <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
                This verification link is invalid, already used, or has expired.
              </p>
              <Link to="/bidder/verify-email" className="btn btn-primary btn-block">Request a new link</Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
