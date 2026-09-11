import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCapabilities } from "../api";
import { useAuth } from "../authContext";
import { ErrorBox } from "../components";
import { SkeletonLine, SkeletonTable } from "../Skeleton";

export default function StatusPage() {
  const { session } = useAuth();
  const [body, setBody] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCapabilities().then(setBody).catch(setError);
  }, []);

  return (
    <div className="page">
      <h1>Verification capabilities</h1>
      <p className="hint">
        What this deployment can and cannot verify right now, stated plainly.
        Nothing here is simulated -- a row with no status is a capability
        nobody has configured yet, not one that silently passes.
      </p>
      {!session && (
        <p className="actions">
          <Link to="/login">Sign in →</Link> to register bidders, verify documents, and review tenders.
        </p>
      )}
      <ErrorBox error={error} />
      {!body && !error && (
        <div className="stack">
          <SkeletonLine width="50%" />
          <SkeletonTable rows={6} columns={6} />
        </div>
      )}
      {body && (
        <>
          <p className={body.live_count > 0 ? "status" : "hint"}>
            {body.live_count} of {body.capabilities.filter((c) => c.capability_id).length} capabilities LIVE.
            {body.note ? ` ${body.note}` : ""}
          </p>
          <div className="table-scroll">
            <table className="evidence-table">
              <thead>
                <tr>
                  <th>Authority</th>
                  <th>Capability</th>
                  <th>Status</th>
                  <th>Tier</th>
                  <th>Channel</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {body.capabilities.map((c) => (
                  <tr key={c.adapter_id}>
                    <td>{c.authority}</td>
                    <td>{c.capability_id || "—"}</td>
                    <td>
                      <span className={`badge ${c.status === "LIVE" ? "v-pass" : c.status === "UNAVAILABLE" ? "v-fail" : "v-unknown"}`}>
                        {c.status}
                      </span>
                    </td>
                    <td>{c.tier || "—"}</td>
                    <td>{c.channel || "—"}</td>
                    <td className="details">{c.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
