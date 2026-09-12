import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { changePassword } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { formatIndianMobile } from "../components/FormControls";
import { Card, ErrorState, Field, PageHeader } from "../../ui/primitives";

function ChangePasswordForm() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setDone(false);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form" onSubmit={onSubmit}>
      <ErrorState error={error} />
      {done && <p className="text-sm" style={{ color: "var(--status-pass-fg)" }}>Password updated.</p>}
      <div className="field">
        <label htmlFor="pw-current">Current password</label>
        <input id="pw-current" type="password" autoComplete="current-password" value={currentPassword}
               onChange={(e) => setCurrentPassword(e.target.value)} required />
      </div>
      <div className="field">
        <label htmlFor="pw-new">New password</label>
        <input id="pw-new" type="password" autoComplete="new-password" value={newPassword}
               onChange={(e) => setNewPassword(e.target.value)} required />
      </div>
      <button type="submit" className="btn btn-secondary" disabled={submitting}>
        {submitting ? "Updating…" : "Change password"}
      </button>
    </form>
  );
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const { bidder, clearSession } = useBidderSession();

  if (!bidder) {
    return (
      <div className="page page-narrow" style={{ maxWidth: 680 }}>
        <PageHeader eyebrow="Bidder Portal" title="Profile" />
        <Card>
          <p className="text-sm">
            You're not signed in. <Link to="/bidder/login">Sign in</Link> or{" "}
            <Link to="/bidder/signup">create an account</Link> to see your profile.
          </p>
        </Card>
      </div>
    );
  }

  function signOut() {
    clearSession();
    navigate("/bidder/dashboard");
  }

  return (
    <div className="page page-narrow" style={{ maxWidth: 680 }}>
      <PageHeader eyebrow="Bidder Portal" title="Profile" />

      <Card title="Personal information">
        <div className="field-grid">
          <Field label="Full name">{bidder.fullName}</Field>
          <Field label="Email">{bidder.email}</Field>
          <Field label="Mobile">{bidder.mobile ? formatIndianMobile(bidder.mobile) : "—"}</Field>
          <Field label="Email verified">
            {bidder.emailVerified ? "Yes" : <>No — <Link to="/bidder/verify-email">verify now</Link></>}
          </Field>
          <Field label="Mobile verified">
            {bidder.mobileVerified ? "Yes" : <>No — <Link to="/bidder/verify-mobile">verify now</Link></>}
          </Field>
        </div>
      </Card>

      <div style={{ marginTop: 20 }}>
        <Card title="Organization">
          <div className="field-grid">
            <Field label="Company name" empty={!bidder.companyName}>{bidder.companyName || "not provided"}</Field>
            <Field label="GSTIN" empty={!bidder.gstin}>{bidder.gstin || "not provided"}</Field>
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 20 }}>
        <Card title="Security">
          {bidder.googleLinked && !bidder.mobile ? (
            <p className="text-sm text-secondary" style={{ marginBottom: 12 }}>
              This account signed up with Google and has no password set yet.
            </p>
          ) : (
            <ChangePasswordForm />
          )}
          <div style={{ marginTop: 16 }}>
            <button type="button" className="btn btn-danger" onClick={signOut}>Sign out</button>
          </div>
        </Card>
      </div>
    </div>
  );
}
