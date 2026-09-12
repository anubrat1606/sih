import { useEffect, useState } from "react";
import { VerdictBadge } from "../ui/primitives";
import { Icon } from "./Emblems";

// An illustration of the real stages a document passes through, in the
// order the orchestrator actually runs them. Identifier values are masked
// on purpose — this is a diagram of the mechanism, never a record.
const STAGES = [
  { id: "INGEST", label: "Ingest", icon: "upload",
    text: "The PDF is hashed (SHA-256) and stored by content. A DOCUMENT_INGESTED event records who uploaded what, and when." },
  { id: "EXTRACT", label: "Extract", icon: "scan",
    text: "Deterministic grammars locate GSTIN, PAN, CIN and Udyam numbers in the document's real text layer, validate every check digit, and record the exact page and pixel region. No OCR, no model." },
  { id: "VERIFY", label: "Verify", icon: "shield",
    text: "Each identifier is put to its issuing authority, live. Where an authority can't be reached, the answer is UNKNOWN with a machine-readable reason — never a guess." },
  { id: "EVALUATE", label: "Evaluate", icon: "scale",
    text: "The tender's adopted rule pack runs over the evidence. Every requirement resolves to PASS, FAIL, PARTIAL or UNKNOWN; coverage, compliance and risk are reported as three separate figures." },
  { id: "DECIDE", label: "Decide", icon: "stamp",
    text: "A procuring officer records QUALIFY or DISQUALIFY with a note. The decision is one more event on the hash chain. The software never decides." },
];

const ROWS = [
  { field: "GSTIN", masked: "24•••••••••1Z•", authority: "GST_STATUS", live: true, verdict: "PASS" },
  { field: "PAN", masked: "•••••1234•", authority: "PAN_STATUS", live: true, verdict: "PASS" },
  { field: "CIN", masked: "U•••••••2019PTC••••••", authority: "CIN_STATUS", live: true, verdict: "PASS" },
  { field: "Udyam", masked: "UDYAM-••-••-•••••••", authority: "UDYAM_STATUS", live: false, verdict: "UNKNOWN" },
];

function RowStatus({ row, stage }) {
  if (stage === 0) return <span className="lp-doc-meta lp-fade-in" key="q">queued</span>;
  if (stage === 1) return <span className="lp-doc-meta lp-fade-in" key="l">located · p.1</span>;
  if (stage === 2) {
    return (
      <span className={`lp-doc-meta lp-fade-in ${row.live ? "lp-doc-live" : ""}`} key="v">
        {row.live ? "authority answered" : "awaiting credentials"}
      </span>
    );
  }
  return <span className="lp-fade-in" key="b"><VerdictBadge verdict={row.verdict} /></span>;
}

export default function Pipeline() {
  const [active, setActive] = useState(0);
  const [manual, setManual] = useState(false);
  const [hovering, setHovering] = useState(false);
  const [reduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);

  useEffect(() => {
    if (manual || hovering || reduced) return undefined;
    const id = setInterval(() => setActive((a) => (a + 1) % STAGES.length), 3400);
    return () => clearInterval(id);
  }, [manual, hovering, reduced]);

  function choose(i) { setManual(true); setActive(i); }

  function onKey(e) {
    const last = STAGES.length - 1;
    if (e.key === "ArrowRight") choose(active === last ? 0 : active + 1);
    else if (e.key === "ArrowLeft") choose(active === 0 ? last : active - 1);
    else if (e.key === "Home") choose(0);
    else if (e.key === "End") choose(last);
    else return;
    e.preventDefault();
  }

  const stage = STAGES[active];

  return (
    <div className="lp-pipe" onMouseEnter={() => setHovering(true)} onMouseLeave={() => setHovering(false)}
         onFocus={() => setHovering(true)} onBlur={() => setHovering(false)}>
      <div className="lp-pipe-head">
        <strong>One document, five stages</strong>
        <span className="mono">SHA-256 · computed on ingest</span>
      </div>

      <div className="lp-pipe-tabs" role="tablist" aria-label="Pipeline stages" onKeyDown={onKey}>
        {STAGES.map((s, i) => (
          <button key={s.id} type="button" role="tab" id={`lp-tab-${s.id}`} aria-selected={i === active}
                  aria-controls="lp-pipe-panel" tabIndex={i === active ? 0 : -1}
                  className={`lp-pipe-tab${i === active ? " is-active" : ""}${i < active ? " is-done" : ""}`}
                  onClick={() => choose(i)}>
            <span className="n" aria-hidden="true">{i < active ? "✓" : i + 1}</span>
            <span className="lbl">{s.label}</span>
          </button>
        ))}
      </div>
      <div className="lp-pipe-track" aria-hidden="true">
        <div className="lp-pipe-fill" style={{ transform: `scaleX(${active / (STAGES.length - 1)})` }} />
      </div>

      <div className="lp-doc" aria-hidden="true">
        {ROWS.map((row) => (
          <div className="lp-doc-row" key={row.field}>
            <span className="lp-doc-field">{row.field}</span>
            <span className="lp-doc-val">
              <span className="mono">{row.masked}</span>
              {active >= 2 && <span className="lp-doc-meta mono">{row.authority}</span>}
            </span>
            <span className="lp-doc-status"><RowStatus row={row} stage={active} /></span>
          </div>
        ))}
        {active === 4 && (
          <div className="lp-doc-decision lp-fade-in">
            <span className="lp-stamp"><Icon name="stamp" size={14} /> QUALIFY · recorded by officer</span>
            <span className="lp-doc-meta">event appended · chain verified</span>
          </div>
        )}
      </div>

      <div className="lp-pipe-panel" role="tabpanel" id="lp-pipe-panel" aria-labelledby={`lp-tab-${stage.id}`}>
        <h3><Icon name={stage.icon} size={18} /> {active + 1}. {stage.label}</h3>
        <p key={stage.id} className="lp-fade-in">{stage.text}</p>
      </div>
      <div className="lp-pipe-caption">Illustration of the stages · not a live record · Udyam status shown UNKNOWN because no lawful API exists for it</div>
    </div>
  );
}
