import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createTender, listTenders, uploadTenderDocument } from "../api";
import { ErrorBox } from "../components";
import { EmptyState } from "../EmptyState";
import { useToast } from "../notifications";
import { SearchFilterBar } from "../SearchFilterBar";
import { SkeletonLine } from "../Skeleton";

const TENDER_CATEGORIES = ["Goods", "Works", "Services", "Consultancy"];

export default function TendersPage() {
  const navigate = useNavigate();
  const { notify } = useToast();
  const [tenders, setTenders] = useState(null);
  const [filtered, setFiltered] = useState(null);
  const [error, setError] = useState(null);
  const [jumpTo, setJumpTo] = useState("");
  const [form, setForm] = useState({
    tender_id: "", title: "", issuing_authority: "", bid_submission_deadline: "", description: "",
    department: "", category: "", issue_date: "",
  });
  const [tenderPdf, setTenderPdf] = useState(null);
  const [creating, setCreating] = useState(false);

  function load() {
    listTenders().then((body) => setTenders(body.tenders)).catch(setError);
  }

  useEffect(load, []);

  // SearchFilterBar wants plain objects to match/sort against -- listTenders()
  // returns bare tender_id strings, so each one is wrapped for the control
  // without changing what's actually rendered below.
  const tenderItems = useMemo(() => (tenders || []).map((t) => ({ tender_id: t })), [tenders]);

  function onJump(e) {
    e.preventDefault();
    if (jumpTo.trim()) navigate(`/tenders/${encodeURIComponent(jumpTo.trim())}`);
  }

  async function onCreate(e) {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      await createTender(form.tender_id, form.title, form.issuing_authority,
        form.bid_submission_deadline, form.description,
        { department: form.department, category: form.category, issueDate: form.issue_date });
      if (tenderPdf) {
        // Best-effort second step: the tender itself is already created and
        // real even if this upload fails, so a failure here is surfaced but
        // does not roll back tender creation -- the officer can retry the
        // upload from the tender's own page (Tender Intelligence needs a
        // document hash, uploaded any time before decomposing).
        try {
          await uploadTenderDocument(form.tender_id, tenderPdf);
        } catch (uploadErr) {
          notify(`Tender created, but the PDF upload failed: ${uploadErr.message}`, { kind: "error" });
        }
      }
      notify(`Created tender ${form.tender_id}.`, { kind: "success" });
      setForm({ tender_id: "", title: "", issuing_authority: "", bid_submission_deadline: "", description: "",
        department: "", category: "", issue_date: "" });
      setTenderPdf(null);
      navigate(`/tenders/${encodeURIComponent(form.tender_id)}`);
    } catch (err) {
      setError(err);
      notify("Could not create the tender.", { kind: "error" });
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page">
      <h1>Tenders</h1>
      <p className="hint">
        Create a tender here to give it a title, issuing authority and bid submission
        deadline before any bidder registers -- or skip that and just register a bidder
        directly on a new tender ID; either way it shows up below.
      </p>
      <ErrorBox error={error} />

      {tenders === null && (
        <div className="stack">
          <SkeletonLine width="60%" />
          <SkeletonLine width="45%" />
          <SkeletonLine width="70%" />
        </div>
      )}
      {tenders && tenders.length === 0 && (
        <EmptyState message="No tenders yet." actionLabel="Register a bidder to start one" actionTo="/register" />
      )}
      {tenders && tenders.length > 0 && (
        <>
          <SearchFilterBar
            items={tenderItems}
            searchKeys={["tender_id"]}
            sortOptions={[
              { label: "A → Z", compare: (a, b) => a.tender_id.localeCompare(b.tender_id) },
              { label: "Z → A", compare: (a, b) => b.tender_id.localeCompare(a.tender_id) },
            ]}
            onChange={setFiltered}
            placeholder="Search tenders…"
          />
          {filtered && filtered.length === 0 ? (
            <p className="hint">No tenders match that search.</p>
          ) : (
            <ul>
              {(filtered || tenderItems).map((t) => (
                <li key={t.tender_id}><Link to={`/tenders/${encodeURIComponent(t.tender_id)}`} className="mono">{t.tender_id}</Link></li>
              ))}
            </ul>
          )}
        </>
      )}

      <h2>Create a tender</h2>
      <form className="form" onSubmit={onCreate}>
        <label>Tender ID<input value={form.tender_id} onChange={(e) => setForm({ ...form, tender_id: e.target.value })} required /></label>
        <label>Title<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></label>
        <label>Issuing authority<input value={form.issuing_authority} onChange={(e) => setForm({ ...form, issuing_authority: e.target.value })} required /></label>
        <label>Department / organization (optional)
          <input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
        </label>
        <label>Tender category (optional)
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">— unspecified —</option>
            {TENDER_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label>Issue date (optional)<input type="date" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} /></label>
        <label>Bid submission deadline (optional)<input type="date" value={form.bid_submission_deadline} onChange={(e) => setForm({ ...form, bid_submission_deadline: e.target.value })} /></label>
        <label>Description (optional)<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label>Tender PDF (optional — you can also add this from the tender's own page)
          <input type="file" accept="application/pdf" onChange={(e) => setTenderPdf(e.target.files?.[0] || null)} />
        </label>
        <button type="submit" disabled={creating}>{creating ? "Creating…" : "Create tender"}</button>
      </form>

      <h2>Jump to a tender</h2>
      <form className="form" onSubmit={onJump}>
        <label>Tender ID<input value={jumpTo} onChange={(e) => setJumpTo(e.target.value)} required /></label>
        <button type="submit">Go</button>
      </form>
    </div>
  );
}
