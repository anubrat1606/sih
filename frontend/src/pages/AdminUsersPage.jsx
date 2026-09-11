import { useState } from "react";
import { createOfficerAccount } from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { ErrorBox } from "../components";
import { useToast } from "../notifications";

const ROLES = ["OFFICER", "SENIOR_OFFICER", "ADMIN"];

export default function AdminUsersPage() {
  const { session } = useAuth();
  const { notify } = useToast();
  const isAdmin = roleAtLeast(session.role, "ADMIN");

  const [form, setForm] = useState({ username: "", password: "", display_name: "", role: "OFFICER" });
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isAdmin) {
    return (
      <div className="page">
        <h1>Officer accounts</h1>
        <p className="hint">
          Creating an account requires ADMIN — you're signed in as {session.role.replace("_", " ")}.
        </p>
      </div>
    );
  }

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
    <div className="page page-narrow">
      <h1>Officer accounts</h1>
      <p className="hint">
        There is no self-signup — every officer's account is created here, by an
        administrator. SENIOR_OFFICER can adopt rule packs and override verdicts;
        a plain OFFICER can register bidders and record QUALIFY/DISQUALIFY decisions
        but not either of those two.
      </p>
      <ErrorBox error={error} />
      <form className="form" onSubmit={onSubmit}>
        <label>Username
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        </label>
        <label>Display name
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required />
        </label>
        <label>Temporary password
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} />
        </label>
        <label>Role
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </select>
        </label>
        <button type="submit" disabled={submitting}>{submitting ? "Creating…" : "Create account"}</button>
      </form>
      {created && (
        <p className="status">
          Created {created.display_name} (<span className="mono">{created.username}</span>), {created.role.replace("_", " ")}.
          Share the temporary password with them directly — it isn't shown again here.
        </p>
      )}
    </div>
  );
}
