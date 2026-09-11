import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listTenders } from "../api";
import { ErrorBox } from "../components";

export default function TendersPage() {
  const navigate = useNavigate();
  const [tenders, setTenders] = useState(null);
  const [error, setError] = useState(null);
  const [jumpTo, setJumpTo] = useState("");

  useEffect(() => {
    listTenders().then((body) => setTenders(body.tenders)).catch(setError);
  }, []);

  function onJump(e) {
    e.preventDefault();
    if (jumpTo.trim()) navigate(`/tenders/${encodeURIComponent(jumpTo.trim())}`);
  }

  return (
    <div className="page">
      <h1>Tenders</h1>
      <p className="hint">
        A tender only exists here once a bidder has been registered on it -- there is
        no separate Tender Management module (see docs/STATUS.md).
      </p>
      <ErrorBox error={error} />

      {tenders && tenders.length === 0 && (
        <p className="hint">No tenders yet. <Link to="/register">Register a bidder</Link> to start one.</p>
      )}
      {tenders && tenders.length > 0 && (
        <ul>
          {tenders.map((t) => (
            <li key={t}><Link to={`/tenders/${encodeURIComponent(t)}`}>{t}</Link></li>
          ))}
        </ul>
      )}

      <h2>Jump to a tender</h2>
      <form className="form" onSubmit={onJump}>
        <label>Tender ID<input value={jumpTo} onChange={(e) => setJumpTo(e.target.value)} required /></label>
        <button type="submit">Go</button>
      </form>
    </div>
  );
}
