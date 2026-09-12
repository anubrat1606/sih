import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  decomposeTender, getAuditExport, getTender, getTenderBlockers, getTenderCollusion,
  getCollusionEdges, listTenderBidders, uploadTenderDocument,
} from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { useApi } from "../lib/useApi";
import { documentsFrom, formatBytes, formatDate, formatTimestamp, parseAuditExport, rulePacksByTender, summarizeEvent } from "../lib/audit";
import { useToast } from "../notifications";
import { RequirementBuilder } from "../features/RequirementBuilder";
import { DataTable } from "../ui/DataTable";
import {
  Callout, Card, Dash, EmptyState, ErrorState, Field, LoadingBlock, PageHeader,
  RiskBadge, Section, Tabs, Tag, UnavailableNote,
} from "../ui/primitives";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "requirements", label: "Requirements" },
  { id: "documents", label: "Documents" },
  { id: "bidders", label: "Bidders" },
  { id: "compliance", label: "Compliance" },
  { id: "evidence", label: "Evidence" },
  { id: "audit", label: "Audit" },
];

function UploadTenderPdf({ tenderId, onUploaded }) {
  const { notify } = useToast();
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = await uploadTenderDocument(tenderId, file);
      setResult(body);
      setFile(null);
      e.target.reset();
      notify("Tender document uploaded.", { kind: "success" });
      onUploaded?.(body);
    } catch (err) {
      setError(err);
      notify("Upload failed.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Tender document">
      <p className="text-secondary text-sm" style={{ marginBottom: 12 }}>
        The authoritative source for every requirement decomposed from this tender. Stored by content
        hash, so a requirement can always be traced back to the exact page it came from.
      </p>
      <ErrorState error={error} />
      <form className="row" style={{ gap: 12, flexWrap: "wrap" }} onSubmit={submit}>
        <input type="file" accept="application/pdf" aria-label="Tender PDF"
               onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ maxWidth: 340 }} />
        <button type="submit" className="btn btn-primary" disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload tender PDF"}
        </button>
      </form>
      {result && (
        <Callout strong>
          Uploaded. Document hash <span className="mono">{result.document_sha256.slice(0, 24)}…</span>,
          recorded as event #{result.seq}.
        </Callout>
      )}
    </Card>
  );
}

export default function TenderDetailPage() {
  const { tenderId } = useParams();
  const { session } = useAuth();
  const { notify } = useToast();
  const [params, setParams] = useSearchParams();
  const activeTab = params.get("tab") || "overview";
  const canAdopt = roleAtLeast(session.role, "SENIOR_OFFICER");

  const tender = useApi(() => getTender(tenderId), [tenderId]);
  const bidders = useApi(() => listTenderBidders(tenderId), [tenderId]);
  const audit = useApi(() => getAuditExport(), [tenderId]);
  const blockers = useApi(() => getTenderBlockers(tenderId).catch((e) => { throw e; }), [tenderId]);
  const collusion = useApi(() => getTenderCollusion(tenderId), [tenderId]);
  const edges = useApi(() => getCollusionEdges(tenderId), [tenderId]);

  const [decomposeResult, setDecomposeResult] = useState(null);
  const [decomposing, setDecomposing] = useState(false);

  const events = useMemo(
    () => (audit.data ? parseAuditExport(audit.data).filter((e) => e.tender_id === tenderId) : []),
    [audit.data, tenderId]
  );
  const pack = useMemo(() => rulePacksByTender(events)[tenderId] || null, [events, tenderId]);
  const documents = useMemo(() => documentsFrom(events), [events]);
  const tenderDoc = documents.find((d) => d.declared_type === "TENDER_NOTICE") || documents[0] || null;

  function setTab(id) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  }

  async function runDecompose() {
    if (!tenderDoc) return;
    setDecomposing(true);
    try {
      const result = await decomposeTender(tenderId, tenderDoc.sha256);
      setDecomposeResult(result);
      if (!result.available) notify(`Suggestions unavailable: ${result.reason}`, { kind: "info" });
      setTab("requirements");
    } catch (err) {
      notify(`Could not read the document: ${err.message}`, { kind: "error" });
    } finally {
      setDecomposing(false);
    }
  }

  const t = tender.data;
  const bidderRows = bidders.data?.bidders || null;

  return (
    <div className="page">
      <PageHeader
        eyebrow={<Link to="/tenders">Tenders</Link>}
        title={t?.title || tenderId}
        subtitle={t?.description}
        actions={
          <>
            {tenderDoc && (
              <button type="button" className="btn btn-secondary" onClick={runDecompose} disabled={decomposing}>
                {decomposing ? "Reading document…" : "Read requirements from PDF"}
              </button>
            )}
            <button type="button" className="btn btn-secondary" onClick={() => setTab("documents")}>
              Upload tender PDF
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setTab("requirements")}>
              Manage requirements
            </button>
          </>
        }
      />

      <ErrorState error={tender.error} onRetry={tender.reload} />

      {/* Identity strip — the record's own facts, always visible above the tabs. */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          {tender.loading ? <LoadingBlock lines={2} /> : (
            <div className="field-grid">
              <Field label="Tender ID"><span className="mono">{tenderId}</span></Field>
              <Field label="Organization" empty={!t?.issuing_authority}>{t?.issuing_authority || "not recorded"}</Field>
              <Field label="Department" empty={!t?.department}>{t?.department || "not recorded"}</Field>
              <Field label="Category">{t?.category ? <Tag>{t.category}</Tag> : <span className="text-muted">not recorded</span>}</Field>
              <Field label="Issue date" empty={!t?.issue_date}>
                {t?.issue_date ? <span className="mono">{formatDate(t.issue_date)}</span> : "not stated"}
              </Field>
              <Field label="Submission deadline" empty={!t?.bid_submission_deadline}>
                {t?.bid_submission_deadline ? <span className="mono">{formatDate(t.bid_submission_deadline)}</span> : "not stated"}
              </Field>
            </div>
          )}
        </div>
        <div className="card-footer">
          <div className="row-wrap" style={{ justifyContent: "space-between" }}>
            <span className="row" style={{ gap: 10 }}>
              <span className="field-label" style={{ margin: 0 }}>Rule pack</span>
              {pack ? (
                <>
                  <Tag accent>ADOPTED</Tag>
                  <span className="mono text-sm">{pack.version}</span>
                  <span className="text-xs text-muted">
                    {pack.requirement_count} requirement(s) · adopted by {pack.officer} · {formatTimestamp(pack.at)}
                  </span>
                </>
              ) : (
                <>
                  <Tag>NOT ADOPTED</Tag>
                  <span className="text-xs text-muted">
                    No rule pack is governing this tender yet — bidders cannot be evaluated until one is adopted.
                  </span>
                </>
              )}
            </span>
            {pack && <button type="button" className="btn btn-sm btn-secondary" onClick={() => setTab("requirements")}>View rule pack</button>}
          </div>
        </div>
      </div>

      <Tabs
        tabs={TABS.map((tab) => ({
          ...tab,
          count: tab.id === "bidders" ? bidderRows?.length
               : tab.id === "documents" ? documents.length
               : tab.id === "audit" ? events.length
               : undefined,
        }))}
        active={activeTab}
        onChange={setTab}
      />

      {activeTab === "overview" && (
        <div className="grid-2">
          <Card title="Bidder summary">
            {bidders.loading ? <LoadingBlock lines={3} /> : !bidderRows?.length ? (
              <p className="text-secondary text-sm">No bidders registered on this tender yet.</p>
            ) : (
              <div className="stack-sm">
                {bidderRows.slice(0, 6).map((b) => (
                  <div key={b.bidder_id} className="row" style={{ justifyContent: "space-between" }}>
                    <Link to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(tenderId)}`} className="mono">
                      {b.bidder_id}
                    </Link>
                    <RiskBadge level={b.risk?.level} />
                  </div>
                ))}
                {bidderRows.length > 6 && (
                  <button type="button" className="btn btn-sm btn-ghost" onClick={() => setTab("bidders")}>
                    View all {bidderRows.length}
                  </button>
                )}
              </div>
            )}
          </Card>

          <Card title="Compliance blockers">
            {blockers.loading ? <LoadingBlock lines={3} /> : blockers.error ? (
              <UnavailableNote title="Not measurable yet">
                Blockers can only be computed once a rule pack is adopted and at least one bidder has been
                evaluated against it.
              </UnavailableNote>
            ) : !blockers.data?.blockers?.length ? (
              <p className="text-secondary text-sm">Nothing is currently blocking a bidder on this tender.</p>
            ) : (
              <div className="stack-sm">
                {blockers.data.blockers.slice(0, 6).map((b) => (
                  <div key={b.requirement_id} className="row" style={{ justifyContent: "space-between" }}>
                    <span className="mono text-sm">{b.requirement_id}</span>
                    <span className="text-sm text-secondary">
                      {b.blocked_bidder_count} bidder(s) · {b.classifications.join(", ")}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {activeTab === "requirements" && (
        canAdopt ? (
          <RequirementBuilder
            tenderId={tenderId}
            issuingAuthority={t?.issuing_authority}
            sourceDocumentSha256={tenderDoc?.sha256}
            suggestions={decomposeResult}
            onAdopted={() => { audit.reload(); }}
          />
        ) : (
          <UnavailableNote title="Adopting a rule pack requires SENIOR OFFICER or higher">
            You are signed in as {session.role.replace("_", " ")}. You can review everything on this tender,
            but requirement adoption is deliberately restricted — a rule pack governs every bidder's
            evaluation, not one bidder's record.
          </UnavailableNote>
        )
      )}

      {activeTab === "documents" && (
        <div className="stack" style={{ gap: 20 }}>
          <UploadTenderPdf tenderId={tenderId} onUploaded={() => audit.reload()} />
          <DataTable
            rows={documents}
            loading={audit.loading}
            error={audit.error}
            getRowKey={(d) => `${d.seq}`}
            searchPlaceholder="Search documents…"
            emptyTitle="No documents ingested"
            emptyMessage="Upload the tender notice to begin decomposing its requirements."
            columns={[
              { key: "file", header: "Document", searchValue: (d) => d.filename, sortValue: (d) => d.filename,
                render: (d) => <span className="cell-primary">{d.filename}</span> },
              { key: "type", header: "Type", sortValue: (d) => d.declared_type,
                render: (d) => (d.declared_type ? <Tag>{d.declared_type}</Tag> : <Dash />) },
              { key: "bidder", header: "Bidder", sortValue: (d) => d.bidder_id,
                render: (d) => d.bidder_id ? <span className="mono">{d.bidder_id}</span> : <span className="text-muted text-sm">tender-level</span> },
              { key: "size", header: "Size", sortValue: (d) => d.bytes,
                render: (d) => <span className="mono text-sm">{formatBytes(d.bytes)}</span> },
              { key: "hash", header: "SHA-256", searchValue: (d) => d.sha256,
                render: (d) => <span className="mono text-xs">{d.sha256.slice(0, 16)}…</span> },
              { key: "at", header: "Ingested", sortValue: (d) => d.seq,
                render: (d) => <span className="mono text-xs">{formatTimestamp(d.occurred_at)}</span> },
            ]}
          />
        </div>
      )}

      {activeTab === "bidders" && (
        <DataTable
          rows={bidderRows}
          loading={bidders.loading}
          error={bidders.error}
          getRowKey={(b) => b.bidder_id}
          searchPlaceholder="Search bidders…"
          emptyTitle="No bidders registered"
          emptyMessage="Register a bidder against this tender to begin evaluating their submission."
          emptyAction={<Link className="btn btn-primary" to={`/bidders/register?tender_id=${encodeURIComponent(tenderId)}`}>Register a bidder</Link>}
          columns={[
            { key: "id", header: "Bidder", sortValue: (b) => b.bidder_id, searchValue: (b) => b.bidder_id,
              render: (b) => (
                <Link to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(tenderId)}`} className="mono">
                  {b.bidder_id}
                </Link>
              ) },
            { key: "compliance", header: "Compliance", sortValue: (b) => b.metrics?.compliance_score,
              render: (b) => b.metrics?.compliance_score == null
                ? <span className="text-muted text-sm">not determined</span>
                : <span className="mono">{Math.round(b.metrics.compliance_score)}%</span> },
            { key: "coverage", header: "Verification coverage", sortValue: (b) => b.metrics?.verification_coverage,
              render: (b) => b.metrics?.verification_coverage == null
                ? <span className="text-muted text-sm">—</span>
                : <span className="mono">{Math.round(b.metrics.verification_coverage)}%</span> },
            { key: "confidence", header: "Evidence confidence", sortValue: (b) => b.metrics?.evidence_confidence,
              render: (b) => b.metrics?.evidence_confidence == null
                ? <span className="text-muted text-sm">—</span>
                : <span className="mono">{Math.round(b.metrics.evidence_confidence)}%</span> },
            { key: "risk", header: "Risk", sortValue: (b) => ({ LOW: 0, MEDIUM: 1, HIGH: 2 }[b.risk?.level] ?? 9),
              render: (b) => <RiskBadge level={b.risk?.level} /> },
            { key: "collusion", header: "Common entity", sortValue: (b) => (b.collusion?.flagged ? 1 : 0),
              render: (b) => b.collusion?.flagged
                ? <Tag>SHARED ATTRIBUTE</Tag>
                : <span className="text-muted text-sm">none detected</span> },
            { key: "actions", header: "", align: "right",
              render: (b) => (
                <Link className="btn btn-sm btn-secondary"
                      to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(tenderId)}`}>
                  Open
                </Link>
              ) },
          ]}
        />
      )}

      {activeTab === "compliance" && (
        <div className="stack" style={{ gap: 20 }}>
          <Section title="Blocking requirements"
                   note="Requirements currently preventing one or more bidders from qualifying, ranked by how many bidders they block.">
            {blockers.loading ? <LoadingBlock /> : blockers.error ? (
              <UnavailableNote title="No rule pack adopted yet">
                A tender's compliance picture only exists once a rule pack governs it and bidders have been
                evaluated against that pack.
              </UnavailableNote>
            ) : !blockers.data?.blockers?.length ? (
              <EmptyState glyph="✓" title="No blockers"
                          message="Nothing is currently blocking a bidder on this tender." />
            ) : (
              <DataTable
                rows={blockers.data.blockers}
                getRowKey={(b) => b.requirement_id}
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
          </Section>

          <Section title="Common-entity signals"
                   note="Bidders on this tender that share a director name, address, phone or bank account. A shared attribute is a signal for an officer to review — never a finding of fraud.">
            {collusion.loading ? <LoadingBlock /> : !edges.data?.edges?.length ? (
              <EmptyState glyph="⚏" title="No shared attributes detected"
                          message="No two bidders on this tender share a tracked attribute." />
            ) : (
              <DataTable
                rows={edges.data.edges}
                getRowKey={(e) => `${e.bidder_a}-${e.bidder_b}-${e.attribute}`}
                columns={[
                  { key: "a", header: "Bidder A", render: (e) => <span className="mono">{e.bidder_a}</span> },
                  { key: "b", header: "Bidder B", render: (e) => <span className="mono">{e.bidder_b}</span> },
                  { key: "attr", header: "Shared attribute", render: (e) => <Tag>{e.attribute}</Tag> },
                  { key: "note", header: "", render: () => (
                    <span className="text-xs text-muted">Potential common entity — requires officer review</span>
                  ) },
                ]}
              />
            )}
          </Section>
        </div>
      )}

      {activeTab === "evidence" && (
        <Section title="Evidence"
                 note="Evidence is held per bidder — open a bidder to walk the chain from requirement to source document, or open their evidence graph.">
          {!bidderRows?.length ? (
            <EmptyState glyph="⌕" title="No evidence yet"
                        message="Evidence appears once a bidder has been registered and their documents ingested." />
          ) : (
            <div className="grid-3">
              {bidderRows.map((b) => (
                <Link key={b.bidder_id} className="card card-link"
                      to={`/bidders/${encodeURIComponent(b.bidder_id)}/evidence-graph?tender_id=${encodeURIComponent(tenderId)}`}>
                  <div className="card-body">
                    <div className="mono" style={{ fontWeight: 600 }}>{b.bidder_id}</div>
                    <p className="text-sm text-secondary" style={{ marginTop: 6 }}>
                      Open the evidence graph — requirements, the evidence each consumes, and which authority
                      was asked.
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Section>
      )}

      {activeTab === "audit" && (
        <Section title="Audit trail for this tender"
                 note="Every event recorded against this tender, in order, hash-chained and insert-only.">
          {audit.loading ? <LoadingBlock /> : events.length === 0 ? (
            <EmptyState glyph="≣" title="No events yet" />
          ) : (
            <Card flush>
              <div style={{ padding: "8px 20px" }}>
                <div className="timeline">
                  {[...events].sort((a, b) => b.seq - a.seq).map((e) => (
                    <div className="timeline-item" key={e.seq}>
                      <div className="timeline-rail"><span className="timeline-dot" /><span className="timeline-line" /></div>
                      <div className="timeline-body">
                        <div className="timeline-head">
                          <span className="timeline-type">{e.event_type}</span>
                          <Tag>{e.actor_kind}</Tag>
                          <span className="timeline-meta mono">{e.actor_id} · #{e.seq} · {formatTimestamp(e.occurred_at)}</span>
                        </div>
                        <div className="timeline-detail">{summarizeEvent(e)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </Section>
      )}
    </div>
  );
}
