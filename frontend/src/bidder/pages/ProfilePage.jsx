// bidderApi.js has no tender-independent "who am I" call, and this page
// isn't scoped to any one tender the way Submit documents is -- so
// display_name/username/role come from the session already held by
// authContext (zero extra call), and only the bidder_id -- which no
// bidderApi.js function returns without a tender_id -- falls back to
// api.js's getMe() directly. auth.jsx's own AuthProvider already imports
// getMe from api.js the same way to revalidate a stored session, so this
// isn't a new pattern in the codebase; it's flagged in the PR as a
// bidderApi.js surface gap worth closing with a getMyProfile()-style
// wrapper, rather than worked around further here.
import { getMe } from "../../api";
import { useApi } from "../../lib/useApi";
import {
  Card, Dash, ErrorState, Field, PageHeader, Section, Tag, UnavailableNote,
} from "../../ui/primitives";
import { useAuth } from "../../authContext";

// Three honest sections: what the account actually is, what the bidder
// record actually has on file (and a plain statement of what it doesn't,
// rather than a blank), and the verification/security features this
// deployment genuinely doesn't have yet (round 6 decision 2 — provisioned
// accounts, no self-service verification infrastructure).

export default function ProfilePage() {
  const { session, logout } = useAuth();
  const me = useApi(() => getMe(), []);

  return (
    <div className="page">
      <PageHeader eyebrow="Bidder" title="Profile" />

      <ErrorState error={me.error} onRetry={me.reload} />

      <Section title="Account">
        <Card>
          <div className="form-row">
            <Field label="Display name">{session?.displayName || <Dash />}</Field>
            <Field label="Username">{session?.username || <Dash />}</Field>
            <Field label="Role"><Tag>{session?.role || "BIDDER"}</Tag></Field>
            <Field label="Bidder ID">
              {me.loading ? (
                <span className="text-secondary text-sm">Loading…</span>
              ) : (
                <span className="mono">{me.data?.bidder_id || <Dash />}</span>
              )}
            </Field>
          </div>
        </Card>
      </Section>

      <Section
        title="Organisation"
        note="This deployment's bidder-facing endpoints don't yet expose the registration attributes (director name, address, phone, bank account) an officer entered at registration, or a way to read back the identifiers extracted from your documents after upload — both are shown honestly below rather than guessed at or left silently blank."
      >
        <Card>
          <div className="form-row">
            <Field label="Bidder ID">
              <span className="mono">{me.data?.bidder_id || <Dash />}</span>
            </Field>
          </div>
          <UnavailableNote title="Registration details">
            Not available from this page yet. Contact the procuring office if you need
            to confirm what's on file.
          </UnavailableNote>
          <UnavailableNote title="Extracted identifiers (GSTIN / PAN / CIN)">
            These are shown to you at the moment you upload a document during
            submission — this page doesn't yet have a way to read them back
            afterward. A future change could add a "structure checked" badge here
            using the same check applied during upload.
          </UnavailableNote>
        </Card>
      </Section>

      <Section
        title="Verification status"
        note="Honest, not aspirational — round 6 deliberately ships with provisioned accounts only. See docs/NEXT_TASKS_6, decision 2."
      >
        <Card>
          <div className="form-row">
            <Field label="Email">
              <UnavailableNote>Not available on this deployment.</UnavailableNote>
            </Field>
            <Field label="Mobile">
              <UnavailableNote>Not available on this deployment.</UnavailableNote>
            </Field>
            <Field label="Organisation">
              <UnavailableNote>Not available on this deployment.</UnavailableNote>
            </Field>
          </div>
        </Card>
      </Section>

      <Section title="Security">
        <Card>
          <div className="btn-group" style={{ flexWrap: "wrap", alignItems: "flex-start" }}>
            <div>
              <UnavailableNote title="Change password">
                Not available on this deployment — there is no endpoint for it yet.
                Contact the procuring office if you need your password reset.
              </UnavailableNote>
            </div>
          </div>
          <button type="button" className="btn btn-secondary" style={{ marginTop: "var(--space-4)" }}
                  onClick={logout}>
            Sign out
          </button>
        </Card>
      </Section>
    </div>
  );
}
