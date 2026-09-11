import { useState } from "react";
import { decomposeTender } from "./api";
import { ErrorBox } from "./components";

// Roadmap A4. A narrator for candidates, not a judge: every proposal here
// is the model's best guess at what the tender document says, re-typed by
// hand into the rule pack builder above if an officer agrees with it.
// Nothing from this component ever reaches POST /tenders/{id}/rule-pack
// directly.
export default function TenderIntelligence({ tenderId, onUseProposal }) {
  const [documentSha256, setDocumentSha256] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function onPropose(e) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      setResult(await decomposeTender(tenderId, documentSha256.trim()));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <details className="tender-intelligence">
      <summary>Tender Intelligence — propose requirements from a document (experimental)</summary>
      <p className="hint">
        Reads a tender document's real text and proposes candidate requirements —
        it never adopts anything. Review each one against the source, then add the
        ones you agree with by hand in the builder above.
      </p>
      <ErrorBox error={error} />
      <form className="form" onSubmit={onPropose}>
        <label>Document SHA-256 <span className="hint">(from an already-uploaded document)</span>
          <input className="mono" value={documentSha256} onChange={(e) => setDocumentSha256(e.target.value)}
                 pattern="[0-9a-f]{64}" required />
        </label>
        <button type="submit" disabled={loading}>{loading ? "Reading document…" : "Propose requirements"}</button>
      </form>

      {result && !result.available && (
        <p className="hint">Not available: {result.reason}</p>
      )}
      {result?.available && (
        <>
          <p className="hint">Narrated by {result.model} at {result.generated_at}. {result.proposals.length} candidate(s).</p>
          {result.proposals.map((p, i) => (
            <div key={i} className="rule-pack-requirement">
              <p>{p.text}</p>
              <p className="hint mono">
                page {p.page} · {p.obligation_guess}
                {p.suggested_field && ` · ${p.suggested_field}`}
                {p.suggested_check && ` (${p.suggested_check})`}
              </p>
              {p.note && <p className="hint">{p.note}</p>}
              {onUseProposal && (
                <button type="button" onClick={() => onUseProposal(p)}>
                  Use this → add as a draft requirement below
                </button>
              )}
            </div>
          ))}
        </>
      )}
    </details>
  );
}
