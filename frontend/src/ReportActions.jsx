import { useState } from "react";
import { getTenderReportCsv, getTenderBlockers } from "./api";
import "./reportActions.css";

function triggerCsvDownload(tenderId, csvText) {
  const blob = new Blob([csvText], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${tenderId}-report.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Round 4, R4. Two backend endpoints live and tested since round 3 with no
// UI caller before this. Both actions are independently loading/error-state
// aware. Suhani's toast system (S1) isn't confirmed merged yet, so this uses
// a plain inline error message -- the documented fallback -- rather than
// blocking on her PR.
export function ReportActions({ tenderId }) {
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvError, setCsvError] = useState(null);

  const [blockers, setBlockers] = useState(null); // null = hidden/not fetched
  const [blockersBusy, setBlockersBusy] = useState(false);
  const [blockersError, setBlockersError] = useState(null);

  async function downloadCsv() {
    setCsvBusy(true);
    setCsvError(null);
    try {
      const csvText = await getTenderReportCsv(tenderId);
      triggerCsvDownload(tenderId, csvText);
    } catch (err) {
      setCsvError(err);
    } finally {
      setCsvBusy(false);
    }
  }

  async function toggleBlockers() {
    if (blockers !== null) {
      setBlockers(null);
      return;
    }
    setBlockersBusy(true);
    setBlockersError(null);
    try {
      const body = await getTenderBlockers(tenderId);
      setBlockers(body.blockers);
    } catch (err) {
      setBlockersError(err);
    } finally {
      setBlockersBusy(false);
    }
  }

  return (
    <div className="report-actions">
      <div className="report-actions-row">
        <button type="button" onClick={downloadCsv} disabled={csvBusy}>
          {csvBusy ? "Preparing…" : "Download CSV"}
        </button>
        <button type="button" onClick={toggleBlockers} disabled={blockersBusy}>
          {blockersBusy ? "Loading…" : blockers !== null ? "Hide blockers" : "Show blockers"}
        </button>
      </div>
      {csvError && <p className="error">{String(csvError.message || csvError)}</p>}
      {blockersError && <p className="error">{String(blockersError.message || blockersError)}</p>}

      {blockers !== null && (
        blockers.length === 0 ? (
          <p className="hint">No blockers -- nothing is currently blocking a bidder on this tender.</p>
        ) : (
          <table className="evidence-table">
            <thead>
              <tr><th>Requirement</th><th>Bidders blocked</th><th>Classifications</th></tr>
            </thead>
            <tbody>
              {blockers.map((row) => (
                <tr key={row.requirement_id}>
                  <td className="mono">{row.requirement_id}</td>
                  <td className="mono">{row.blocked_bidder_count}</td>
                  <td>{row.classifications.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
