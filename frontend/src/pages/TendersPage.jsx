import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createTender, getAuditExport, getTender, listTenders, uploadTenderDocument } from "../api";
import { useApi } from "../lib/useApi";
import { formatDate, parseAuditExport, rulePacksByTender } from "../lib/audit";
import { useToast } from "../notifications";
import { DataTable } from "../ui/DataTable";
import { Dash, ErrorState, PageHeader, Tag } from "../ui/primitives";

const CATEGORIES = ["Goods", "Works", "Services", "Consultancy"];

function CreateTenderDialog({ open, onClose, onCreated }) {
  const { notify } = useToast();
  const [form, setForm] = useState({
    tender_id: "", title: "", issuing_authority: "", department: "",
    category: "", issue_date: "", bid_submission_deadline: "", description: "",
  });
  const [pdf, setPdf] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!open) return null;

  function set(key, value) { setForm((f) => ({ ...f, [key]: value })); }

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createTender(
        form.tender_id, form.title, form.issuing_authority,
        form.bid_submission_deadline, form.description,
        { department: form.department, category: form.category, issueDate: form.issue_date }
      );
      if (pdf) {
        try {
          await uploadTenderDocument(form.tender_id, pdf);
        } catch (uploadErr) {
          // The tender itself is real and created; say exactly what failed
          // rather than rolling back something that genuinely succeeded.
          notify(`Tender created, but the PDF upload failed: ${uploadErr.message}`, { kind: "error" });
        }
      }
      notify(`Created tender ${form.tender_id}.`, { kind: "success" });
      onCreated(form.tender_id);
    } catch (err) {
      setError(err);
      notify("Could not create the tender.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ maxWidth: 680 }} role="dialog" aria-modal="true"
           aria-label="Create tender" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h2 className="section-title">Create tender</h2>
          <p className="text-secondary text-sm" style={{ marginTop: 6 }}>
            Record the tender exactly as the issuing authority published it. Nothing here is inferred.
          </p>
        </div>
        <form onSubmit={onSubmit}>
          <div className="dialog-body">
            <ErrorState error={error} />
            <div className="form form-wide" style={{ gap: 16 }}>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="t-id">Tender ID / reference number</label>
                  <input id="t-id" className="mono" value={form.tender_id} required
                         onChange={(e) => set("tender_id", e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="t-cat">Category</label>
                  <select id="t-cat" value={form.category} onChange={(e) => set("category", e.target.value)}>
                    <option value="">— unspecified —</option>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div className="field">
                <label htmlFor="t-title">Tender title</label>
                <input id="t-title" value={form.title} required onChange={(e) => set("title", e.target.value)} />
              </div>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="t-org">Issuing authority</label>
                  <input id="t-org" value={form.issuing_authority} required
                         onChange={(e) => set("issuing_authority", e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="t-dept">Department <span className="field-hint">optional</span></label>
                  <input id="t-dept" value={form.department} onChange={(e) => set("department", e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="t-issue">Issue date <span className="field-hint">optional</span></label>
                  <input id="t-issue" type="date" value={form.issue_date} onChange={(e) => set("issue_date", e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="t-deadline">Submission deadline <span className="field-hint">optional</span></label>
                  <input id="t-deadline" type="date" value={form.bid_submission_deadline}
                         onChange={(e) => set("bid_submission_deadline", e.target.value)} />
                </div>
              </div>
              <div className="field">
                <label htmlFor="t-desc">Description <span className="field-hint">optional</span></label>
                <input id="t-desc" value={form.description} onChange={(e) => set("description", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="t-pdf">Tender document (PDF) <span className="field-hint">optional — can also be uploaded later</span></label>
                <input id="t-pdf" type="file" accept="application/pdf"
                       onChange={(e) => setPdf(e.target.files?.[0] || null)} />
              </div>
            </div>
          </div>
          <div className="dialog-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Creating…" : "Create tender"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function TendersPage() {
  const navigate = useNavigate();
  const tenderList = useApi(() => listTenders(), []);
  const audit = useApi(() => getAuditExport(), []);
  const [rows, setRows] = useState(null);
  const [creating, setCreating] = useState(false);
  const [packFilter, setPackFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");

  const packs = useMemo(() => (audit.data ? rulePacksByTender(parseAuditExport(audit.data)) : {}), [audit.data]);

  useEffect(() => {
    const ids = tenderList.data?.tenders;
    if (!ids) return;
    let cancelled = false;
    Promise.all(ids.map((id) => getTender(id).catch(() => ({ tender_id: id }))))
      .then((r) => { if (!cancelled) setRows(r); });
    return () => { cancelled = true; };
  }, [tenderList.data]);

  const filtered = useMemo(() => {
    if (!rows) return null;
    return rows.filter((r) => {
      if (packFilter === "adopted" && !packs[r.tender_id]) return false;
      if (packFilter === "none" && packs[r.tender_id]) return false;
      if (categoryFilter !== "all" && (r.category || "") !== categoryFilter) return false;
      return true;
    });
  }, [rows, packs, packFilter, categoryFilter]);

  const categories = useMemo(() => {
    const set = new Set((rows || []).map((r) => r.category).filter(Boolean));
    return [...set].sort();
  }, [rows]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Procurement"
        title="Tenders"
        subtitle="Every tender recorded in this system, with the rule pack governing how its bids are evaluated."
        actions={<button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>+ Create tender</button>}
      />

      <ErrorState error={tenderList.error} onRetry={tenderList.reload} />

      <DataTable
        rows={filtered}
        loading={tenderList.loading || (tenderList.data && !rows)}
        getRowKey={(r) => r.tender_id}
        searchPlaceholder="Search by ID, title or organization…"
        emptyTitle="No tenders yet"
        emptyMessage="Create a tender to start evaluating bids against a published rule pack."
        emptyAction={<button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>+ Create tender</button>}
        initialSort={{ key: "id", direction: "asc" }}
        filters={[
          {
            id: "pack", label: "Rule pack", value: packFilter, onChange: setPackFilter,
            options: [
              { value: "all", label: "All" },
              { value: "adopted", label: "Adopted" },
              { value: "none", label: "Not adopted" },
            ],
          },
          ...(categories.length ? [{
            id: "cat", label: "Category", value: categoryFilter, onChange: setCategoryFilter,
            options: [{ value: "all", label: "All" }, ...categories.map((c) => ({ value: c, label: c }))],
          }] : []),
        ]}
        columns={[
          {
            key: "id", header: "Tender ID", sortValue: (r) => r.tender_id, searchValue: (r) => r.tender_id,
            render: (r) => <Link to={`/officials/tenders/${encodeURIComponent(r.tender_id)}`} className="mono">{r.tender_id}</Link>,
          },
          {
            key: "title", header: "Tender", sortValue: (r) => r.title, searchValue: (r) => r.title,
            render: (r) => r.title ? <span className="cell-primary">{r.title}</span> : <Dash />,
          },
          {
            key: "org", header: "Organization", sortValue: (r) => r.issuing_authority, searchValue: (r) => r.issuing_authority,
            render: (r) => r.issuing_authority || <Dash />,
          },
          {
            key: "dept", header: "Department", sortValue: (r) => r.department,
            render: (r) => r.department || <Dash />,
          },
          {
            key: "cat", header: "Category", sortValue: (r) => r.category,
            render: (r) => (r.category ? <Tag>{r.category}</Tag> : <Dash />),
          },
          {
            key: "deadline", header: "Submission deadline", sortValue: (r) => r.bid_submission_deadline,
            render: (r) => r.bid_submission_deadline
              ? <span className="mono">{formatDate(r.bid_submission_deadline)}</span>
              : <span className="text-muted text-sm">not stated</span>,
          },
          {
            key: "pack", header: "Rule pack", sortValue: (r) => (packs[r.tender_id] ? 1 : 0),
            render: (r) => {
              const p = packs[r.tender_id];
              return p
                ? <span className="mono text-xs" title={p.version}>{p.semver} · {p.requirement_count} req</span>
                : <span className="text-muted text-sm">not adopted</span>;
            },
          },
          {
            key: "status", header: "Status", sortValue: (r) => (packs[r.tender_id] ? "Evaluating" : "Draft"),
            render: (r) => packs[r.tender_id]
              ? <Tag accent>EVALUATING</Tag>
              : <Tag>AWAITING RULE PACK</Tag>,
          },
          {
            key: "actions", header: "", align: "right",
            render: (r) => (
              <Link to={`/officials/tenders/${encodeURIComponent(r.tender_id)}`} className="btn btn-sm btn-secondary">Open</Link>
            ),
          },
        ]}
      />

      <CreateTenderDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(id) => { setCreating(false); navigate(`/officials/tenders/${encodeURIComponent(id)}`); }}
      />
    </div>
  );
}
