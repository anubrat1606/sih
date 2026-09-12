
import { Link } from "react-router-dom";
import { getAuditExport, getTender, getTenderBlockers, listTenderBidders, listTenders } from "../api";
import { useApi } from "../lib/useApi";
import { parseAuditExport, rulePacksByTender } from "../lib/audit";
import { DataTable } from "../ui/DataTable";
import {
  Card, EmptyState, ErrorState, LoadingBlock, PageHeader, RiskBadge, Section, Stat, Tag, UnavailableNote,
} from "../ui/primitives";

// Compliance across every tender: which requirements are blocking bidders,
// and where a tender cannot be measured at all yet because no rule pack
// governs it. "Not measurable" is stated as such — never counted as zero.
export default function CompliancePage() {
  const audit = useApi(() => getAuditExport(), []);
  // One composite read: each tender with its blockers and bidders. A tender
  // with no adopted rule pack returns null blockers — "not measurable",
  // which is rendered as exactly that and never counted as zero.
  const overview = useApi(async () => {
    const { tenders: ids } = await listTenders();
    return Promise.all((ids || []).map(async (id) => {
      const [meta, blockers, bidders] = await Promise.all([
        getTender(id).catch(() => ({ tender_id: id })),
        getTenderBlockers(id).then((b) => b.blockers).catch(() => null),
        listTenderBidders(id).then((b) => b.bidders || []).catch(() => []),
      ]);
      return { ...meta, blockers, bidders };
    }));
  }, []);

  const packs = audit.data ? rulePacksByTender(parseAuditExport(audit.data)) : {};
  const tenders = overview.data;

  const measurable = (tenders || []).filter((t) => t.blockers !== null);
  const totalBlockers = measurable.reduce((sum, t) => sum + t.blockers.length, 0);
  const totalBidders = (tenders || []).reduce((sum, t) => sum + t.bidders.length, 0);
  const highRisk = (tenders || []).reduce(
    (sum, t) => sum + t.bidders.filter((b) => b.risk?.level === "HIGH").length, 0
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Evaluation"
        title="Compliance"
        subtitle="Where bids stand against the rule packs governing them, across every tender in the system."
      />

      <ErrorState error={overview.error} onRetry={overview.reload} />

      <div className="stat-row">
        <Stat label="Tenders measurable" value={tenders ? measurable.length : null}
              accent="neutral" note={tenders ? `${tenders.length - measurable.length} awaiting a rule pack` : undefined} />
        <Stat label="Blocking requirements" value={tenders ? totalBlockers : null} accent={totalBlockers ? "fail" : "pass"} />
        <Stat label="Bidders evaluated" value={tenders ? totalBidders : null} accent="neutral" />
        <Stat label="High risk" value={tenders ? highRisk : null} accent={highRisk ? "fail" : "pass"} />
      </div>

      {overview.loading ? <div style={{ marginTop: 24 }}><LoadingBlock /></div> : !tenders?.length ? (
        <div style={{ marginTop: 24 }}>
          <EmptyState glyph="◌" title="No tenders yet"
                      message="Compliance is measured per tender. Create one to begin."
                      action={<Link to="/tenders" className="btn btn-primary">Go to tenders</Link>} />
        </div>
      ) : (
        tenders.map((t) => (
          <Section key={t.tender_id}
                   title={<Link to={`/tenders/${encodeURIComponent(t.tender_id)}`}>{t.title || t.tender_id}</Link>}
                   note={<span className="mono text-xs">{t.tender_id}</span>}
                   actions={packs[t.tender_id]
                     ? <Tag accent>{packs[t.tender_id].semver}</Tag>
                     : <Tag>NO RULE PACK</Tag>}>
            {t.blockers === null ? (
              <UnavailableNote title="Not measurable yet">
                No rule pack governs this tender, so there is nothing to evaluate its bids against. This is a
                stated gap, not a score of zero.
              </UnavailableNote>
            ) : t.blockers.length === 0 ? (
              <Card>
                <p className="text-sm text-secondary">
                  Nothing is currently blocking a bidder on this tender
                  {t.bidders.length ? ` (${t.bidders.length} bidder(s) evaluated).` : "."}
                </p>
              </Card>
            ) : (
              <DataTable
                rows={t.blockers}
                getRowKey={(b) => `${t.tender_id}-${b.requirement_id}`}
                initialSort={{ key: "count", direction: "desc" }}
                columns={[
                  { key: "req", header: "Requirement", sortValue: (b) => b.requirement_id, searchValue: (b) => b.requirement_id,
                    render: (b) => <span className="mono">{b.requirement_id}</span> },
                  { key: "count", header: "Bidders blocked", sortValue: (b) => b.blocked_bidder_count,
                    render: (b) => <span className="mono">{b.blocked_bidder_count}</span> },
                  { key: "class", header: "Classification",
                    render: (b) => <span className="row" style={{ gap: 6 }}>{b.classifications.map((c) => <Tag key={c}>{c}</Tag>)}</span> },
                ]}
              />
            )}

            {t.bidders.length > 0 && (
              <div className="grid-3" style={{ marginTop: 12 }}>
                {t.bidders.map((b) => (
                  <Link key={b.bidder_id} className="card card-link"
                        to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(t.tender_id)}`}>
                    <div className="card-body">
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <span className="mono" style={{ fontWeight: 600 }}>{b.bidder_id}</span>
                        <RiskBadge level={b.risk?.level} />
                      </div>
                      <p className="text-xs text-secondary" style={{ marginTop: 8 }}>
                        Compliance{" "}
                        <span className="mono">
                          {b.metrics?.compliance_score == null ? "—" : `${Math.round(b.metrics.compliance_score)}%`}
                        </span>
                        {" · "}Coverage{" "}
                        <span className="mono">
                          {b.metrics?.verification_coverage == null ? "—" : `${Math.round(b.metrics.verification_coverage)}%`}
                        </span>
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Section>
        ))
      )}
    </div>
  );
}
