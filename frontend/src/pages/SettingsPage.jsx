import { useState } from "react";
import { createOfficerAccount, getCapabilities } from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { useApi } from "../lib/useApi";
import { useToast } from "../notifications";
import {
  Callout, Card, CapabilityBadge, ErrorState, Field, PageHeader, Section, Tag, UnavailableNote,
} from "../ui/primitives";

const ROLES = [
  { value: "OFFICER", label: "Officer", note: "Register bidders, upload documents, record QUALIFY / DISQUALIFY decisions." },
  { value: "SENIOR_OFFICER", label: "Senior officer", note: "Everything an officer can do, plus adopt rule packs and override verdicts." },
  { value: "ADMIN", label: "Administrator", note: "Everything, plus creating officer accounts." },
];

export default function SettingsPage() {
  const { session } = useAuth();
  const { notify } = useToast();
  const isAdmin = roleAtLeast(session.role, "ADMIN");
  const capabilities = useApi(() => getCapabilities(), []);

  const [form, setForm] = useState({ username: "", password: "", display_name: "", role: "OFFICER" });
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setCreated(null);
    setSubmitting(true);
    try {
      const user = await createOfficerAccount(form.username, form.password, form.display_name, form.role);
      setCreated(user);
      setForm({ username: "", password: "", display_name: "", role: "OFFICER" });
      notify(`Created account for ${user.display_name}.`, { kind: "success" });
    } catch (err) {
      setError(err);
      notify("Could not create the account.", { kind: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Administration"
        title="Settings"
        subtitle="Your session, this deployment's verification posture, and officer account management."
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

      <Section title="Officer accounts"
               note="There is no self-signup. Every account is created here, by an administrator, with an explicit role.">
        {!isAdmin ? (
          <UnavailableNote title="Creating accounts requires ADMIN">
            You are signed in as {session.role.replace("_", " ")}. Ask an administrator to create an account
            for a new officer.
          </UnavailableNote>
        ) : (
          <div className="grid-2">
            <Card title="Create an officer account">
              <ErrorState error={error} />
              <form className="form" onSubmit={onSubmit}>
                <div className="field">
                  <label htmlFor="a-user">Username</label>
                  <input id="a-user" className="mono" value={form.username} required
                         onChange={(e) => setForm({ ...form, username: e.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="a-name">Display name</label>
                  <input id="a-name" value={form.display_name} required
                         onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="a-pass">
                    Temporary password <span className="field-hint">at least 8 characters</span>
                  </label>
                  <input id="a-pass" type="password" value={form.password} required minLength={8}
                         onChange={(e) => setForm({ ...form, password: e.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="a-role">Role</label>
                  <select id="a-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                    {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                  <span className="field-hint">{ROLES.find((r) => r.value === form.role)?.note}</span>
                </div>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? "Creating…" : "Create account"}
                </button>
              </form>
              {created && (
                <Callout strong>
                  Created {created.display_name} (<span className="mono">{created.username}</span>),
                  {" "}{created.role.replace("_", " ")}. Share the temporary password with them directly —
                  it is not shown again here.
                </Callout>
              )}
            </Card>

            <Card title="What each role can do">
              <div className="stack">
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
        )}
      </Section>
    </div>
  );
}
