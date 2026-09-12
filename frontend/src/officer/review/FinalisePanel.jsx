import { useState } from "react";
import { getBidderResultPreview, recordDecision } from "../../api";
import { useAuth } from "../../authContext";
import { useApi } from "../../lib/useApi";
import { formatTimestamp } from "../../lib/audit";
import { useToast } from "../../notifications";
import { Callout, Card, ConfirmDialog, VerdictBadge } from "../../ui/primitives";

// The officer's finalise step (round 6): shows exactly what the bidder
// will see once a decision is recorded -- via GET .../result-preview,
// the SAME projection GET /me/tenders/{id}/result uses, not a
// hand-built guess at it -- then the decision control itself. Once
// decided, the control locks: a second decision is a new event, not an
// edit, so there is nothing left here to "change."
export default function FinalisePanel({ bidderId, tenderId }) {
  const { session } = useAuth();
  const { notify } = useToast();
  const preview = useApi(() => getBidderResultPreview(tenderId, bidderId), [bidderId, tenderId]);
  const [note, setNote] = useState("");
  const [confirmDisqualify, setConfirmDisqualify] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState(null);

  const decided = preview.data?.published;

  async function decide(decision) {
    setError(null);
    setRecording(true);
    try {
      await recordDecision(bidderId, tenderId, decision, note);
      notify(`Recorded: ${decision}. Now visible to the bidder.`, { kind: decision === "QUALIFY" ? "success" : "info" });
      preview.reload();
    } catch (err) {
      setError(err);
      notify("Could not record the decision.", { kind: "error" });
    } finally {
      setRecording(false);
    }
  }

  return (
    <Card title="Finalise">
      <p className="text-secondary text-sm" style={{ marginBottom: 12 }}>
        What {bidderId} will see the moment this is recorded — the exact same view their own
        portal reads, not a separate summary of it.
      </p>

      {preview.loading && <p className="hint">Loading…</p>}
      {error && <p className="error-note" role="alert"><span aria-hidden="true">⚠</span> {error.message}</p>}

      {!preview.loading && !decided && (
        <Callout>Not yet decided — the bidder currently sees only their submission status, nothing evaluative.</Callout>
      )}

      {decided && (
        <>
          <Callout strong>
            Decided: {preview.data.decision} — visible to the bidder as of{" "}
            {formatTimestamp(preview.data.decided_at)}.
          </Callout>
          {preview.data.note && <p className="text-sm" style={{ marginTop: 8 }}>Note shown to the bidder: “{preview.data.note}”</p>}
          {preview.data.outcomes?.length > 0 && (
            <table className="evidence-table" style={{ marginTop: 12 }}>
              <thead><tr><th>Requirement</th><th>Outcome</th></tr></thead>
              <tbody>
                {preview.data.outcomes.map((o) => (
                  <tr key={o.requirement_id}>
                    <td className="mono">{o.requirement_id}</td>
                    <td><VerdictBadge verdict={o.verdict} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <div className="form" style={{ marginTop: 16 }}>
        <div className="field">
          <label htmlFor="finalise-note">Note to the bidder <span className="field-hint">optional</span></label>
          <input id="finalise-note" value={note} disabled={decided || recording}
                 onChange={(e) => setNote(e.target.value)} />
        </div>
        <p className="text-xs text-muted">
          Recorded as {session.displayName} ({session.role.replace("_", " ")}). A decision is a
          separate, permanent event — recording another does not edit this one.
        </p>
        <div className="btn-group">
          <button type="button" className="btn btn-primary" disabled={decided || recording}
                  onClick={() => decide("QUALIFY")}>
            {decided ? "Decided" : "Qualify"}
          </button>
          <button type="button" className="btn btn-danger" disabled={decided || recording}
                  onClick={() => setConfirmDisqualify(true)}>
            Disqualify
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDisqualify}
        title="Disqualify this bidder?"
        body={`This records a DISQUALIFY decision for ${bidderId} on ${tenderId}, attributed to ${session.displayName}, and becomes visible in their portal immediately.`}
        confirmLabel="Disqualify"
        danger
        onConfirm={() => { setConfirmDisqualify(false); decide("DISQUALIFY"); }}
        onCancel={() => setConfirmDisqualify(false)}
      />
    </Card>
  );
}
