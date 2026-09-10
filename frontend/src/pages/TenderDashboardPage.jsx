import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { adoptRulePack, listTenderBidders } from "../api";
import { ErrorBox, Metric, RiskBadge } from "../components";

export default function TenderDashboardPage() {
  const { tenderId } = useParams();
  const [bidders, setBidders] = useState(null);
  const [error, setError] = useState(null);
  const [officerId, setOfficerId] = useState("officer_demo");
  const [packText, setPackText] = useState("");
  const [adoptResult, setAdoptResult] = useState(null);
  const [violations, setViolations] = useState(null);

  function load() {
    listTenderBidders(tenderId).then((body) => setBidders(body.bidders)).catch(setError);
  }

  useEffect(load, [tenderId]);

  async function onAdopt(e) {
    e.preventDefault();
    setError(null);
    setViolations(null);
    try {
      let pack;
      try {
        pack = JSON.parse(packText);
      } catch {
        throw new Error("rule pack must be valid JSON -- see schemas/rule_pack.schema.json");
      }
      setAdoptResult(await adoptRulePack(tenderId, officerId, pack));
    } catch (err) {
      if (err.detail?.violations) setViolations(err.detail.violations);
      else setError(err);
    }
  }

  return (
    <div className="page">
      <h1>Tender {tenderId}</h1>
      <ErrorBox error={error} />

      <h2>Bidders</h2>
      {bidders && bidders.length === 0 && <p className="hint">No bidders registered yet.</p>}
      <div className="card-grid">
        {bidders && bidders.map((b) => (
          <Link className="card" key={b.bidder_id} to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(tenderId)}`}>
            <h2>{b.bidder_id}</h2>
            <RiskBadge level={b.risk.level} />
            <div className="metric-row">
              <Metric label="Compliance" value={b.metrics.compliance_score} />
              <Metric label="Coverage" value={b.metrics.verification_coverage} />
              <Metric label="Confidence" value={b.metrics.evidence_confidence} />
            </div>
            {b.collusion?.flagged && <p className="flag">Collusion flagged: {b.collusion.cluster_id}</p>}
          </Link>
        ))}
      </div>

      <h2>Adopt a rule pack</h2>
      <p className="hint">
        Rule packs are versioned, content-addressed data (docs/RULE_PACKS.md), not code --
        paste one matching /schemas/rule_pack.schema.json. Adopting a new version never
        mutates a past verdict.
      </p>
      <form className="form" onSubmit={onAdopt}>
        <label>Officer ID<input value={officerId} onChange={(e) => setOfficerId(e.target.value)} required /></label>
        <label>Rule pack JSON
          <textarea rows={10} value={packText} onChange={(e) => setPackText(e.target.value)} placeholder='{"rule_pack_id": "...", "semver": "1.0.0", "requirements": [...]}' required />
        </label>
        <button type="submit">Adopt</button>
      </form>
      {adoptResult && <p className="status">Adopted rule pack version {adoptResult.rule_pack_version}.</p>}
      {violations && (
        <div className="error">
          <p>Rule pack refused -- {violations.length} violation(s):</p>
          <ul>
            {violations.map((v, i) => (
              <li key={i}>[{v.rule}] {v.requirement_id ? `${v.requirement_id}: ` : ""}{v.message}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
