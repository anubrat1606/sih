import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTenderBidders } from "../api";

const RISK_COLOR = { LOW: "#1a7f37", MEDIUM: "#b08800", HIGH: "#cf222e" };

export default function DashboardPage() {
  const { tenderId } = useParams();
  const [bidders, setBidders] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTenderBidders(tenderId)
      .then(setBidders)
      .catch((err) => setError(String(err.message || err)))
      .finally(() => setLoading(false));
  }, [tenderId]);

  return (
    <div className="page">
      <h1>Tender {tenderId} — Officer Dashboard</h1>
      {loading && <p>Loading real bidder scores...</p>}
      {error && <p className="error">Error: {error}</p>}
      <div className="card-grid">
        {bidders.map((b) => (
          <Link to={`/bidder/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(tenderId)}`} key={b.bidder_id} className="card">
            <h2>{b.bidder_id}</h2>
            <p className="score">{b.compliance_score}/100</p>
            <p style={{ color: RISK_COLOR[b.risk_level] || "#666", fontWeight: 600 }}>{b.risk_level} RISK</p>
            {b.collusion_flag?.flagged && <p className="flag">⚠ Collusion signal</p>}
          </Link>
        ))}
      </div>
      {!loading && bidders.length === 0 && !error && <p>No bidders verified yet for this tender.</p>}
    </div>
  );
}
