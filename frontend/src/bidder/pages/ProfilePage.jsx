import { useState } from "react";
import { Link } from "react-router-dom";
import { BackendNotImplementedError, changePassword } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { formatIndianMobile } from "../components/FormControls";
import { BackendPendingInline, BackendPendingNotice } from "../components/BackendPendingNotice";
import { Card, Field, PageHeader } from "../../ui/primitives";

export default function ProfilePage() {
  const { profile, setProfile } = useBidderSession();
  const [pwPending, setPwPending] = useState(null);

  async function onChangePassword(e) {
    e.preventDefault();
    try {
      await changePassword();
    } catch (err) {
      setPwPending(err);
    }
  }

  if (!profile) {
    return (
      <div className="page page-narrow" style={{ maxWidth: 680 }}>
        <PageHeader eyebrow="Bidder Portal" title="Profile" />
        <Card>
          <p className="text-sm">
            No local profile is saved in this browser yet. <Link to="/bidder/signup">Create an account</Link> to
            start one — note bidder accounts aren't live on the backend, so this stays a local draft until they are.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="page page-narrow" style={{ maxWidth: 680 }}>
      <PageHeader eyebrow="Bidder Portal" title="Profile" subtitle="A local draft only — see the notice below." />

      <BackendPendingNotice endpoint="GET /bidders/auth/me">
        There is no bidder account system on the backend, so nothing here is a real, server-verified profile.
        What's shown below is exactly what was entered on Sign Up, kept in this browser only.
      </BackendPendingNotice>

      <div style={{ marginTop: 20 }}>
        <Card title="Personal information">
          <div className="field-grid">
            <Field label="Full name">{profile.fullName}</Field>
            <Field label="Email">{profile.email}</Field>
            <Field label="Mobile">{profile.mobile ? formatIndianMobile(profile.mobile) : "—"}</Field>
            <Field label="Email verified">{profile.emailVerified ? "Yes" : "No"}</Field>
            <Field label="Mobile verified">{profile.mobileVerified ? "Yes" : "No"}</Field>
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 20 }}>
        <Card title="Organization">
          <div className="field-grid">
            <Field label="Company name">{profile.companyName || "—"}</Field>
            <Field label="GSTIN" empty={!profile.gstin}>{profile.gstin || "not provided"}</Field>
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 20 }}>
        <Card title="Security">
          <form onSubmit={onChangePassword}>
            <button type="submit" className="btn btn-secondary">Change password</button>
          </form>
          {pwPending instanceof BackendNotImplementedError && (
            <BackendPendingInline endpoint={pwPending.requiredEndpoint}>{pwPending.message}</BackendPendingInline>
          )}
          <div style={{ marginTop: 16 }}>
            <button type="button" className="btn btn-danger" onClick={() => setProfile(null)}>
              Clear local profile
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}
