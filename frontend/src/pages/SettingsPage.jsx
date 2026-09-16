import { Link } from "react-router-dom";
import { getCapabilities } from "../api";
import { useAuth } from "../authContext";
import { useApi } from "../lib/useApi";
import { Card, CapabilityBadge, ErrorState, Field, PageHeader, Tag } from "../ui/primitives";

const ROLES = [
  { value: "BIDDER", label: "Bidder", note: "Signs in as one specific registered bidder — their own tenders, requirements, submissions and results only." },
  { value: "OFFICER", label: "Officer", note: "Register bidders, upload documents, record QUALIFY / DISQUALIFY decisions." },
  { value: "SENIOR_OFFICER", label: "Senior officer", note: "Everything an officer can do, plus adopt rule packs and override verdicts." },
  { value: "ADMIN", label: "Administrator", note: "Everything, plus the admin console: every account, and this deployment's live posture." },
];

// Account creation, the account directory, and disable/enable moved to the
// admin console (round 7, /admin/accounts) -- a second copy of that form
// here would just be one more place for the two to drift apart. This page
// stays what it was for everyone else: your own session, and what this
// deployment can currently verify.
export default function SettingsPage() {
  const { session } = useAuth();
  const isAdmin = session.role === "ADMIN";
  const capabilities = useApi(() => getCapabilities(), []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Administration"
        title="Settings"
        subtitle="Your session and this deployment's verification posture."
      />

      <div className="grid-2">
        <Card title="Your session">
          <div className="field-grid">
            <Field label="Signed in as">{session.displayName}</Field>
            <Field label="Username"><span className="mono">{session.username}</span></Field>
            <Field label="Role"><Tag accent>{session.role.replace("_", " ")}</Tag></Field>
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 14 }}>
            Every write you make is attributed to this identity in the audit trail, permanently.
          </p>
          {isAdmin && (
            <p className="text-sm" style={{ marginTop: 14 }}>
              <Link to="/admin/accounts">Manage accounts in the admin console →</Link>
            </p>
          )}
        </Card>

        <Card title="Deployment verification posture">
          {capabilities.loading ? <p className="text-sm text-secondary">Loading…</p> : capabilities.error ? (
            <ErrorState error={capabilities.error} onRetry={capabilities.reload} />
          ) : (
            <div className="stack-sm">
              {capabilities.data.capabilities.map((c) => (
                <div key={c.adapter_id} className="row" style={{ justifyContent: "space-between", gap: 12 }}>
                  <span className="text-sm">{c.capability_id || c.authority}</span>
                  <CapabilityBadge status={c.status} />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div style={{ marginTop: 24 }}>
        <Card title="What each role can do">
          <div className="grid-2">
            {ROLES.map((r) => (
              <div key={r.value}>
                <div className="row" style={{ gap: 8, marginBottom: 4 }}>
                  <Tag accent={r.value === "ADMIN"}>{r.label}</Tag>
                </div>
                <p className="text-sm text-secondary">{r.note}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
