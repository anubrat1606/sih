import { useState } from "react";
import { Link } from "react-router-dom";
import { getAuditVerify, getCapabilities, listAccounts, listBidderIds, listTenders } from "../../api";
import { useApi } from "../../lib/useApi";
import { useToast } from "../../notifications";
import {
  Card, ErrorState, LoadingBlock, PageHeader, Section, Stat,
} from "../../ui/primitives";

const STATUS_LABEL = { LIVE: "Live", AWAITING_CREDENTIALS: "Awaiting credentials", UNAVAILABLE: "No lawful source" };

function AuthorityRow({ c }) {
  return (
    <div className="admin-authority-row">
      <span className={`admin-authority-dot admin-authority-dot-${c.status.toLowerCase()}`} aria-hidden="true" />
      <span className="admin-authority-name">{c.authority}</span>
      <span className="mono text-xs text-muted">{c.capability_id || "—"}</span>
      <span className={`admin-authority-status admin-authority-status-${c.status.toLowerCase()}`}>
        {STATUS_LABEL[c.status] || c.status}
      </span>
    </div>
  );
}

// The admin console's front page: what this deployment is, right now, in
// one screen -- accounts, tenders, bidders, live authorities, chain
// integrity. Every number is a live read; nothing here is cached or
// pre-computed for effect.
export default function OverviewPage() {
  const { notify } = useToast();
  const accounts = useApi(listAccounts, []);
  const tenders = useApi(listTenders, []);
  const bidderIds = useApi(listBidderIds, []);
  const capabilities = useApi(getCapabilities, []);
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);

  async function runVerify() {
    setVerifying(true);
    try {
      const body = await getAuditVerify();
      setVerification({ ...body, at: new Date() });
      notify(body.intact ? `Chain intact — ${body.events} events re-hashed.` : "Chain BROKEN — see /admin's audit link.",
        { kind: body.intact ? "success" : "error" });
    } catch (err) {
      notify(`Verification failed to run: ${err.message}`, { kind: "error" });
    } finally {
      setVerifying(false);
    }
  }

  const byRole = (accounts.data?.users || []).reduce((acc, u) => {
    acc[u.role] = (acc[u.role] || 0) + 1;
    return acc;
  }, {});
  const disabledCount = (accounts.data?.users || []).filter((u) => u.disabled).length;
  const liveCount = capabilities.data?.capabilities?.filter((c) => c.status === "LIVE").length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Admin console"
        title="Overview"
        subtitle="This deployment's real posture — accounts, tenders, live verification authorities, and the audit chain's own integrity — read fresh, not summarized in advance."
      />

      <ErrorState error={accounts.error || tenders.error || bidderIds.error} />

      {accounts.loading || tenders.loading || bidderIds.loading ? (
        <LoadingBlock lines={2} />
      ) : (
        <div className="stat-row" style={{ marginBottom: 24 }}>
          <Stat label="Accounts" value={accounts.data?.users?.length ?? "—"}
                note={disabledCount ? `${disabledCount} disabled` : "all active"} accent="neutral" />
          <Stat label="Officers" value={(byRole.OFFICER || 0) + (byRole.SENIOR_OFFICER || 0) + (byRole.ADMIN || 0)}
                note="officer, senior officer, admin" accent="neutral" />
          <Stat label="Bidder accounts" value={byRole.BIDDER || 0} note="provisioned, never self-signed-up" accent="neutral" />
          <Stat label="Tenders" value={tenders.data?.tenders?.length ?? "—"} accent="neutral" />
          <Stat label="Registered bidders" value={bidderIds.data?.bidders?.length ?? "—"}
                note="across every tender" accent="neutral" />
        </div>
      )}

      <div className="grid-2">
        <Section title="Verification authorities"
                 note="Read live from this deployment's capability registry — the same feed the public landing page shows.">
          <Card>
            {capabilities.loading ? <LoadingBlock lines={3} /> : capabilities.error || !capabilities.data ? (
              <p className="text-sm text-muted">Registry unavailable right now.</p>
            ) : (
              <>
                <p className="text-sm text-secondary" style={{ marginBottom: 12 }}>
                  <strong className="text-pass">{liveCount}</strong> of {capabilities.data.capabilities.length} capabilities live.
                </p>
                <div className="admin-authority-list">
                  {capabilities.data.capabilities.map((c) => <AuthorityRow key={c.adapter_id} c={c} />)}
                </div>
              </>
            )}
          </Card>
        </Section>

        <Section title="Audit chain integrity"
                 note="Re-hashes every event in the log against the one before it, right now, in this browser.">
          <Card
            actions={
              <button type="button" className="btn btn-primary btn-sm" onClick={runVerify} disabled={verifying}>
                {verifying ? "Re-hashing…" : "Verify now"}
              </button>
            }
          >
            {!verification ? (
              <p className="text-sm text-muted">Not verified this session yet — click "Verify now."</p>
            ) : (
              <div className="field-grid">
                <div className="field">
                  <span className="field-label">Status</span>
                  <span className={verification.intact ? "text-pass" : "text-fail"} style={{ fontWeight: 700 }}>
                    {verification.intact ? "INTACT" : "BROKEN"}
                  </span>
                </div>
                <div className="field"><span className="field-label">Events re-hashed</span><span className="mono">{verification.rehashed}</span></div>
                <div className="field"><span className="field-label">Links checked</span><span className="mono">{verification.linked}</span></div>
                <div className="field"><span className="field-label">Verified at</span><span className="text-sm">{verification.at.toLocaleTimeString()}</span></div>
              </div>
            )}
            <p className="text-xs text-muted" style={{ marginTop: 14 }}>
              <Link to="/audit">Full event log and chain-break detail →</Link>
            </p>
          </Card>
        </Section>
      </div>
    </div>
  );
}
