import { useState } from "react";
import { Link } from "react-router-dom";
import {
  getAutopsy, getBidderDossier, getTender, getTenderReport, getTenderReportCsv,
  listTenderBidders, listTenders,
} from "../api";
import { useApi } from "../lib/useApi";
import { useToast } from "../notifications";
import {
  Callout, Card, EmptyState, ErrorState, LoadingBlock, MetricCard,
  PageHeader, Section, SeverityBadge, UnavailableNote, VerdictBadge,
} from "../ui/primitives";

function downloadText(filename, text, type = "text/csv") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function TenderComplianceReport({ tenderId }) {
  const report = useApi(() => getTenderReport(tenderId), [tenderId]);
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);

  async function exportCsv() {
    setBusy(true);
    try {
      const csv = await getTenderReportCsv(tenderId);
      downloadText(`${tenderId}-compliance-report.csv`, csv);
      notify("CSV exported.", { kind: "success" });
    } catch (err) {
      notify(`Export failed: ${err.message}`, { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  const r = report.data;
  return (
    <Card
      title="Compliance report"
      actions={
        <button type="button" className="btn btn-sm btn-secondary" onClick={exportCsv} disabled={busy}>
          {busy ? "Preparing…" : "Export CSV"}
        </button>
      }
    >
      {report.loading ? <LoadingBlock lines={3} /> : report.error ? (
        <UnavailableNote title="Report not available yet">
          A tender-wide report is produced once bidders have been evaluated against an adopted rule pack.
        </UnavailableNote>
      ) : (
        <>
          <div className="metric-triad">
            <MetricCard label="Mean compliance" value={r.compliance_score?.mean}
                        note={r.compliance_score?.null_count ? `${r.compliance_score.null_count} bidder(s) not determinate` : undefined} />
            <MetricCard label="Mean evidence confidence" value={r.evidence_confidence?.mean} />
            <MetricCard label="Mean verification coverage" value={r.verification_coverage?.mean} />
          </div>
          <div className="field-grid" style={{ marginTop: 20 }}>
            <div>
              <div className="field-label">Bidders</div>
              <div className="field-value mono">{r.bidder_count}</div>
            </div>
            <div>
              <div className="field-label">Risk distribution</div>
              <div className="field-value mono">
                {r.risk_distribution.LOW} low · {r.risk_distribution.MEDIUM} medium · {r.risk_distribution.HIGH} high
              </div>
            </div>
            <div>
              <div className="field-label">Common-entity clusters</div>
              <div className="field-value mono">
                {r.collusion.cluster_count} cluster(s) · {r.collusion.flagged_bidder_count} bidder(s)
              </div>
            </div>
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 14 }}>
            A mean excludes bidders whose score could not be determined — it is never computed as if an
            undetermined score were zero.
          </p>
        </>
      )}
    </Card>
  );
}

function BidderDocuments({ tenderId, bidderId }) {
  const { notify } = useToast();
  const [dossier, setDossier] = useState(null);
  const [autopsy, setAutopsy] = useState(null);
  const [busy, setBusy] = useState(null);

  async function load(kind) {
    setBusy(kind);
    try {
      if (kind === "dossier") setDossier(await getBidderDossier(bidderId, tenderId));
      else setAutopsy(await getAutopsy(bidderId, tenderId));
    } catch (err) {
      notify(`${kind === "dossier" ? "Dossier" : "Autopsy"} unavailable: ${err.message}`, { kind: "info" });
      if (kind === "dossier") setDossier({ unavailable: err.message });
      else setAutopsy({ unavailable: err.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card
      title={<span className="mono">{bidderId}</span>}
      actions={
        <>
          <button type="button" className="btn btn-sm btn-secondary" disabled={busy === "dossier"}
                  onClick={() => load("dossier")}>
            {busy === "dossier" ? "Loading…" : "Compliance dossier"}
          </button>
          <button type="button" className="btn btn-sm btn-secondary" disabled={busy === "autopsy"}
                  onClick={() => load("autopsy")}>
            {busy === "autopsy" ? "Loading…" : "Bid autopsy report"}
          </button>
        </>
      }
    >
      {!dossier && !autopsy && (
        <p className="text-sm text-secondary">
          Generate the full compliance dossier, or the autopsy explaining exactly why this bid would fail today.
        </p>
      )}

      {dossier && (
        dossier.unavailable ? (
          <UnavailableNote title="Dossier unavailable">{dossier.unavailable}</UnavailableNote>
        ) : (
          <div style={{ marginTop: 8 }}>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
              <h3>Compliance dossier</h3>
              <button type="button" className="btn btn-sm btn-ghost"
                      onClick={() => downloadText(`${bidderId}-dossier.json`, JSON.stringify(dossier, null, 2), "application/json")}>
                Download JSON
              </button>
            </div>
            <pre className="mono" style={{
              background: "var(--color-surface-sunken)", border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)", padding: 16, overflow: "auto",
              maxHeight: 320, fontSize: 12,
            }}>{JSON.stringify(dossier, null, 2)}</pre>
          </div>
        )
      )}

      {autopsy && (
        autopsy.unavailable ? (
          <UnavailableNote title="Autopsy unavailable">{autopsy.unavailable}</UnavailableNote>
        ) : autopsy.would_qualify === null ? (
          <UnavailableNote title="Nothing to analyse">{autopsy.note}</UnavailableNote>
        ) : autopsy.would_qualify ? (
          <Callout strong>Nothing is blocking qualification for this bidder.</Callout>
        ) : (
          <div style={{ marginTop: 12 }}>
            <h3 style={{ marginBottom: 8 }}>Bid autopsy</h3>
            <div className="table-frame">
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>Requirement</th><th>Result</th><th>Severity</th><th>Text</th></tr></thead>
                  <tbody>
                    {autopsy.blocking_requirements.map((b) => (
                      <tr key={b.requirement_id}>
                        <td className="mono">{b.requirement_id}</td>
                        <td><VerdictBadge verdict={b.verdict} /></td>
                        <td><SeverityBadge classification={b.classification} /></td>
                        <td className="cell-note">{b.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )
      )}
    </Card>
  );
}

export default function ReportsPage() {
  const tenderList = useApi(() => listTenders(), []);
  const [chosen, setChosen] = useState("");

  // Default to the first tender without an effect: derive it during render
  // from whatever the list actually returned.
  const ids = tenderList.data?.tenders || [];
  const selected = chosen || ids[0] || "";

  const context = useApi(async () => {
    if (!selected) return null;
    const [meta, bidders] = await Promise.all([
      getTender(selected).catch(() => null),
      listTenderBidders(selected).then((b) => b.bidders || []).catch(() => []),
    ]);
    return { meta, bidders };
  }, [selected], { skip: !selected });

  const meta = context.data?.meta;
  const bidders = context.data?.bidders;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Documentation"
        title="Reports"
        subtitle="Evaluation documents produced from the record itself — never re-generated prose, never a second source of truth."
      />

      <ErrorState error={tenderList.error} onRetry={tenderList.reload} />

      {tenderList.loading ? <LoadingBlock /> : !tenderList.data?.tenders?.length ? (
        <EmptyState glyph="▣" title="No tenders to report on"
                    message="Reports are produced per tender. Create one to begin."
                    action={<Link to="/officials/tenders" className="btn btn-primary">Go to tenders</Link>} />
      ) : (
        <>
          <Card title="Select a tender">
            <div className="field" style={{ maxWidth: 420 }}>
              <label htmlFor="report-tender">Tender</label>
              <select id="report-tender" value={selected} onChange={(e) => setChosen(e.target.value)}>
                {tenderList.data.tenders.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            {meta && (
              <p className="text-sm text-secondary" style={{ marginTop: 12 }}>
                {meta.title} {meta.issuing_authority ? `· ${meta.issuing_authority}` : ""}
              </p>
            )}
          </Card>

          {selected && (
            <>
              <Section title="Tender-wide">
                <TenderComplianceReport tenderId={selected} />
              </Section>

              <Section title="Per bidder"
                       note="A compliance dossier is the complete evidentiary record for one bidder; an autopsy explains exactly what is blocking them.">
                {!bidders ? <LoadingBlock /> : bidders.length === 0 ? (
                  <EmptyState glyph="⚏" title="No bidders on this tender"
                              message="Per-bidder reports appear once bidders are registered and evaluated." />
                ) : (
                  <div className="stack" style={{ gap: 16 }}>
                    {bidders.map((b) => (
                      <BidderDocuments key={b.bidder_id} tenderId={selected} bidderId={b.bidder_id} />
                    ))}
                  </div>
                )}
              </Section>
            </>
          )}
        </>
      )}
    </div>
  );
}
