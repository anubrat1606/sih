import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createTender, listTenders } from "../api";
import { ErrorBox } from "../components";

export default function TendersPage() {
  const navigate = useNavigate();
  const [tenders, setTenders] = useState(null);
  const [error, setError] = useState(null);
  const [jumpTo, setJumpTo] = useState("");
  const [form, setForm] = useState({ tender_id: "", title: "", issuing_authority: "", bid_submission_deadline: "", description: "" });
  const [creating, setCreating] = useState(false);

  function load() {
    listTenders().then((body) => setTenders(body.tenders)).catch(setError);
  }

  useEffect(load, []);

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
        form.bid_submission_deadline, form.description);
      setForm({ tender_id: "", title: "", issuing_authority: "", bid_submission_deadline: "", description: "" });
      load();
    } catch (err) {
      setError(err);
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

      {tenders && tenders.length === 0 && (
        <p className="hint">No tenders yet. Create one below, or <Link to="/register">register a bidder</Link> to start one implicitly.</p>
      )}
      {tenders && tenders.length > 0 && (
        <ul>
          {tenders.map((t) => (
            <li key={t}><Link to={`/tenders/${encodeURIComponent(t)}`} className="mono">{t}</Link></li>
          ))}
        </ul>
      )}

      <h2>Create a tender</h2>
      <form className="form" onSubmit={onCreate}>
        <label>Tender ID<input value={form.tender_id} onChange={(e) => setForm({ ...form, tender_id: e.target.value })} required /></label>
        <label>Title<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></label>
        <label>Issuing authority<input value={form.issuing_authority} onChange={(e) => setForm({ ...form, issuing_authority: e.target.value })} required /></label>
        <label>Bid submission deadline (optional)<input type="date" value={form.bid_submission_deadline} onChange={(e) => setForm({ ...form, bid_submission_deadline: e.target.value })} /></label>
        <label>Description (optional)<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
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
