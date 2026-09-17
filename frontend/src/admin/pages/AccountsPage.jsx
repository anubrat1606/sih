import { useMemo, useState } from "react";
import {
  createOfficerAccount, disableAccount, enableAccount, listAccounts, listBidderIds, resetPassword,
} from "../../api";
import { useAuth } from "../../authContext";
import { useApi } from "../../lib/useApi";
import { useToast } from "../../notifications";
import {
  Card, ConfirmDialog, EmptyState, ErrorState, LoadingBlock, PageHeader, Section, Tag,
} from "../../ui/primitives";

// The one place on this deployment a real secret is ever shown -- exactly
// once, right after the server generates it, never stored or re-fetchable
// afterward. Styled with the app's own .dialog-* classes (see
// ui/primitives.jsx's ConfirmDialog) rather than a bespoke look, but built
// separately from ConfirmDialog since this needs one acknowledgement
// button and a copy affordance, not a confirm/cancel pair.
function PasswordRevealDialog({ result, onClose }) {
  const [copied, setCopied] = useState(false);
  if (!result) return null;

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(result.new_password);
      setCopied(true);
    } catch {
      // Clipboard access can be blocked (permissions, insecure context) --
      // the password stays visible and selectable in the box regardless,
      // so this never blocks the admin from getting it out.
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="Password reset"
           onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header"><h2 className="section-title">Password reset</h2></div>
        <div className="dialog-body">
          <p>New password for <strong>{result.username}</strong>:</p>
          <div className="row" style={{ gap: "var(--space-2)", alignItems: "center", marginTop: "var(--space-3)" }}>
            <code className="mono" style={{
              flex: 1, padding: "var(--space-2) var(--space-3)",
              background: "var(--color-surface-sunken)", border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-sm)", userSelect: "all", wordBreak: "break-all",
            }}>
              {result.new_password}
            </code>
            <button type="button" className="btn btn-sm btn-secondary" onClick={onCopy}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="text-xs text-secondary" style={{ marginTop: "var(--space-3)" }}>
            This won't be shown again — make sure {result.username} has it before you close this.
          </p>
        </div>
        <div className="dialog-footer">
          <button type="button" className="btn btn-primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

const ROLES = [
  { value: "BIDDER", label: "Bidder" },
  { value: "OFFICER", label: "Officer" },
  { value: "SENIOR_OFFICER", label: "Senior officer" },
  { value: "ADMIN", label: "Administrator" },
];

function RoleTag({ role }) {
  return <Tag accent={role === "ADMIN"}>{role.replace("_", " ")}</Tag>;
}

function StatusTag({ disabled }) {
  return disabled
    ? <span className="badge badge-fail"><span className="badge-glyph" aria-hidden="true">✕</span> Disabled</span>
    : <span className="badge badge-pass"><span className="badge-glyph" aria-hidden="true">✓</span> Active</span>;
}

export default function AccountsPage() {
  const { session } = useAuth();
  const { notify } = useToast();
  const accounts = useApi(listAccounts, []);
  const bidderIds = useApi(listBidderIds, []);

  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [pending, setPending] = useState(null); // {username, action: "disable"|"enable"|"reset"}
  const [revealed, setRevealed] = useState(null); // {username, new_password} from a completed reset

  const [form, setForm] = useState({ username: "", password: "", display_name: "", role: "OFFICER", bidder_id: "" });
  const [formError, setFormError] = useState(null);
  const [creating, setCreating] = useState(false);

  const filtered = useMemo(() => {
    const users = accounts.data?.users || [];
    const q = query.trim().toLowerCase();
    return users
      .filter((u) => roleFilter === "all" || u.role === roleFilter)
      .filter((u) => !q || u.username.toLowerCase().includes(q) || u.display_name.toLowerCase().includes(q))
      .slice()
      .reverse(); // newest-created first for a directory; list_users itself is oldest-first
  }, [accounts.data, query, roleFilter]);

  async function onCreate(e) {
    e.preventDefault();
    setFormError(null);
    setCreating(true);
    try {
      await createOfficerAccount(form.username, form.password, form.display_name, form.role, form.bidder_id);
      notify(`Created account for ${form.display_name}.`, { kind: "success" });
      setForm({ username: "", password: "", display_name: "", role: "OFFICER", bidder_id: "" });
      accounts.reload();
    } catch (err) {
      setFormError(err);
    } finally {
      setCreating(false);
    }
  }

  async function confirmPending() {
    const { username, action } = pending;
    setPending(null);
    try {
      if (action === "reset") {
        const result = await resetPassword(username);
        setRevealed(result);
        notify(`Password reset for ${username}.`, { kind: "success" });
      } else {
        await (action === "disable" ? disableAccount(username) : enableAccount(username));
        notify(`${username} ${action}d.`, { kind: "success" });
      }
      accounts.reload();
    } catch (err) {
      notify(`Could not ${action === "reset" ? "reset the password for" : action} ${username}: ${err.message}`,
             { kind: "error" });
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Admin console"
        title="Accounts"
        subtitle="Every officer and bidder account on this deployment. There is no self-signup — every row here was provisioned by an administrator."
      />

      <div className="grid-2">
        <Section title="Directory">
          <ErrorState error={accounts.error} onRetry={accounts.reload} />
          {accounts.loading ? <LoadingBlock lines={5} /> : (
            <Card flush>
              <div className="toolbar">
                <div className="toolbar-search">
                  <input type="search" value={query} placeholder="Search username or name…"
                         aria-label="Search accounts" onChange={(e) => setQuery(e.target.value)} />
                </div>
                <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}
                        aria-label="Filter by role" style={{ width: "auto", minWidth: 160 }}>
                  <option value="all">All roles</option>
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                <span className="toolbar-count mono">{filtered.length} of {accounts.data?.users?.length ?? 0}</span>
              </div>

              {filtered.length === 0 ? (
                <EmptyState glyph="◑" title="No accounts match" message="Try a different search or role filter." />
              ) : (
                <div className="table-frame">
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Account</th><th>Role</th><th>Status</th><th>Created</th><th />
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((u) => {
                          const self = u.username === session.username;
                          return (
                            <tr key={u.username}>
                              <td>
                                <div style={{ fontWeight: 600 }}>{u.display_name}</div>
                                <div className="mono text-xs text-muted">
                                  {u.username}{u.bidder_id && <> · bidder {u.bidder_id}</>}
                                </div>
                              </td>
                              <td><RoleTag role={u.role} /></td>
                              <td><StatusTag disabled={u.disabled} /></td>
                              <td className="text-xs text-muted">
                                {u.created_at ? new Date(u.created_at).toLocaleDateString() : <span>—</span>}
                              </td>
                              <td>
                                <div className="btn-group" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
                                  {!self && (
                                    <button type="button" className={`btn btn-sm ${u.disabled ? "btn-secondary" : "btn-danger"}`}
                                            onClick={() => setPending({ username: u.username, action: u.disabled ? "enable" : "disable" })}>
                                      {u.disabled ? "Enable" : "Disable"}
                                    </button>
                                  )}
                                  <button type="button" className="btn btn-sm btn-secondary"
                                          onClick={() => setPending({ username: u.username, action: "reset" })}>
                                    Reset password
                                  </button>
                                  {self && <span className="text-xs text-muted">this is you</span>}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Card>
          )}
        </Section>

        <Section title="Create an account">
          <Card>
            <ErrorState error={formError} />
            <form className="form" onSubmit={onCreate}>
              <div className="field">
                <label htmlFor="a-name">Display name</label>
                <input id="a-name" value={form.display_name} required
                       onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="a-user">Username</label>
                <input id="a-user" className="mono" value={form.username} required
                       onChange={(e) => setForm({ ...form, username: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="a-pass">Password</label>
                <input id="a-pass" type="password" value={form.password} required minLength={8}
                       onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="a-role">Role</label>
                <select id="a-role" value={form.role}
                        onChange={(e) => setForm({ ...form, role: e.target.value, bidder_id: "" })}>
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              {form.role === "BIDDER" && (
                <div className="field">
                  <label htmlFor="a-bidder">Bidder</label>
                  {bidderIds.data?.bidders?.length ? (
                    <select id="a-bidder" value={form.bidder_id} required
                            onChange={(e) => setForm({ ...form, bidder_id: e.target.value })}>
                      <option value="">— select a registered bidder —</option>
                      {bidderIds.data.bidders.map((b) => (
                        <option key={b.bidder_id} value={b.bidder_id}>{b.bidder_id} ({b.tender_ids.length} tender{b.tender_ids.length === 1 ? "" : "s"})</option>
                      ))}
                    </select>
                  ) : (
                    <input id="a-bidder" className="mono" value={form.bidder_id} required
                           placeholder="no bidders registered yet — type an id"
                           onChange={(e) => setForm({ ...form, bidder_id: e.target.value })} />
                  )}
                </div>
              )}
              <button type="submit" className="btn btn-primary" disabled={creating}>
                {creating ? "Creating…" : "Create account"}
              </button>
            </form>
          </Card>
        </Section>
      </div>

      <ConfirmDialog
        open={!!pending}
        title={pending?.action === "disable" ? "Disable this account?"
          : pending?.action === "enable" ? "Re-enable this account?"
          : "Reset this account's password?"}
        body={pending?.action === "disable"
          ? `${pending?.username} will be signed out immediately and cannot sign in again until re-enabled.`
          : pending?.action === "enable"
          ? `${pending?.username} will be able to sign in again.`
          : `A new random password will be generated for ${pending?.username}. Their current password stops working immediately, and the new one is shown to you only once, right after this.`}
        confirmLabel={pending?.action === "disable" ? "Disable"
          : pending?.action === "enable" ? "Enable" : "Reset password"}
        danger={pending?.action === "disable"}
        onConfirm={confirmPending}
        onCancel={() => setPending(null)}
      />

      <PasswordRevealDialog result={revealed} onClose={() => setRevealed(null)} />
    </div>
  );
}
