// Shared UI primitives for SATYAPRAMĀṆ. Every status surface here carries
// colour + glyph + text label — colour is never the only carrier of
// meaning, so an officer with deuteranopia reads the identical verdict a
// sighted colleague does.

import { Link } from "react-router-dom";

/* ---------------------------------------------------------------- badges */

const VERDICT = {
  PASS: { cls: "badge-pass", glyph: "✓" },
  FAIL: { cls: "badge-fail", glyph: "✕" },
  PARTIAL: { cls: "badge-partial", glyph: "◑" },
  UNKNOWN: { cls: "badge-unknown", glyph: "?" },
};

export function VerdictBadge({ verdict }) {
  const v = VERDICT[verdict] || VERDICT.UNKNOWN;
  return (
    <span className={`badge ${v.cls}`}>
      <span className="badge-glyph" aria-hidden="true">{v.glyph}</span>
      {verdict || "UNKNOWN"}
    </span>
  );
}

const RISK = {
  LOW: { cls: "badge-pass", glyph: "○" },
  MEDIUM: { cls: "badge-partial", glyph: "◑" },
  HIGH: { cls: "badge-fail", glyph: "●" },
};

export function RiskBadge({ level }) {
  const r = RISK[level] || RISK.MEDIUM;
  return (
    <span className={`badge ${r.cls}`}>
      <span className="badge-glyph" aria-hidden="true">{r.glyph}</span>
      {level || "MEDIUM"} RISK
    </span>
  );
}

// Review state of a drafted requirement. APPROVED means an officer has
// cleared it for adoption; REVIEW REQUIRED means the system will refuse to
// adopt it until a human resolves it (rule pack schema rule 11).
export function ReviewBadge({ reviewRequired, evidenceBacked }) {
  if (reviewRequired) {
    return (
      <span className="badge badge-partial">
        <span className="badge-glyph" aria-hidden="true">⚑</span>
        REVIEW REQUIRED
      </span>
    );
  }
  if (evidenceBacked === false) {
    return (
      <span className="badge badge-unknown">
        <span className="badge-glyph" aria-hidden="true">?</span>
        NO EVIDENCE PATH
      </span>
    );
  }
  return (
    <span className="badge badge-pass">
      <span className="badge-glyph" aria-hidden="true">✓</span>
      APPROVED
    </span>
  );
}

// Capability status from GET /capabilities — LIVE / AWAITING_CREDENTIALS /
// UNAVAILABLE, each stated plainly rather than collapsed to a green dot.
export function CapabilityBadge({ status }) {
  const map = {
    LIVE: { cls: "badge-pass", glyph: "✓" },
    AWAITING_CREDENTIALS: { cls: "badge-partial", glyph: "◑" },
    UNAVAILABLE: { cls: "badge-unknown", glyph: "—" },
  };
  const s = map[status] || map.UNAVAILABLE;
  return (
    <span className={`badge ${s.cls}`}>
      <span className="badge-glyph" aria-hidden="true">{s.glyph}</span>
      {status}
    </span>
  );
}

// Bid Autopsy: FATAL is positive evidence against the bidder (re-checking
// the same fact won't change it); CURABLE is an absence of evidence a new
// document could still fill.
export function SeverityBadge({ classification }) {
  const map = {
    FATAL: { cls: "badge-fail", glyph: "✕" },
    CURABLE: { cls: "badge-partial", glyph: "◑" },
  };
  const s = map[classification] || { cls: "badge-unknown", glyph: "?" };
  return (
    <span className={`badge ${s.cls}`}>
      <span className="badge-glyph" aria-hidden="true">{s.glyph}</span>
      {classification || "UNKNOWN"}
    </span>
  );
}

export function Tag({ children, accent }) {
  return <span className={`tag${accent ? " tag-accent" : ""}`}>{children}</span>;
}

/* ------------------------------------------------------------ page parts */

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function Section({ title, note, actions, children }) {
  return (
    <section className="section">
      {(title || actions) && (
        <div className="section-header">
          <div>
            {title && <h2 className="section-title">{title}</h2>}
            {note && <p className="section-note">{note}</p>}
          </div>
          {actions && <div className="btn-group">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Card({ title, actions, children, flush }) {
  return (
    <div className="card">
      {(title || actions) && (
        <div className="card-header">
          <span className="card-title">{title}</span>
          {actions && <div className="btn-group">{actions}</div>}
        </div>
      )}
      <div className={flush ? "card-body card-body-flush" : "card-body"}>{children}</div>
    </div>
  );
}

export function Field({ label, children, empty }) {
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className={`field-value${empty ? " field-value-empty" : ""}`}>{children}</div>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={active === t.id}
          className={`tab${active === t.id ? " tab-active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && t.count !== null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- states */

export function SkeletonLine({ width = "100%" }) {
  return <div className="skeleton skeleton-line" style={{ width }} aria-hidden="true" />;
}

export function LoadingBlock({ label = "Loading…", lines = 4 }) {
  return (
    <div className="card" aria-busy="true" aria-live="polite">
      <div className="card-body">
        <span className="visually-hidden">{label}</span>
        {Array.from({ length: lines }).map((_, i) => (
          <SkeletonLine key={i} width={`${100 - i * 12}%`} />
        ))}
      </div>
    </div>
  );
}

export function LoadingTable({ rows = 5, columns = 5 }) {
  return (
    <div className="table-frame" aria-busy="true">
      <table className="data-table">
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: columns }).map((_, c) => (
                <td key={c}><SkeletonLine width={c === 0 ? "60%" : "85%"} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EmptyState({ glyph = "◌", title, message, action }) {
  return (
    <div className="state-block">
      <div className="state-glyph" aria-hidden="true">{glyph}</div>
      <div className="state-title">{title}</div>
      {message && <p className="state-message">{message}</p>}
      {action}
    </div>
  );
}

// An API failure. Distinct from UNKNOWN: this is "we could not ask", not
// "we asked and the answer is undetermined".
export function ErrorState({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error-note" role="alert">
      <span aria-hidden="true">⚠</span>
      <div>
        <div>{String(error.message || error)}</div>
        {onRetry && (
          <button type="button" className="btn btn-sm btn-secondary" style={{ marginTop: 8 }} onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

// The honest "this could not be determined" surface — bordered, labelled
// and calm, so UNKNOWN reads as a deliberate state, never a broken panel.
export function UnavailableNote({ title, children }) {
  return (
    <div className="unavailable-note">
      <span className="unavailable-note-glyph" aria-hidden="true">?</span>
      <div>
        {title && <strong style={{ color: "var(--color-text)" }}>{title}</strong>}
        {title && <br />}
        {children}
      </div>
    </div>
  );
}

export function Callout({ children, strong }) {
  return <p className={`callout${strong ? " callout-strong" : ""}`}>{children}</p>;
}

// A real, adoptable requirement type whose evidence is still genuinely
// weaker than a register-backed one (self-declared/Tier C, capped at
// PARTIAL) -- distinct from UnavailableNote, which means "cannot be
// adopted at all." Uses the PARTIAL status tokens deliberately, not
// decoratively: these types' own verdict ceiling literally is PARTIAL, so
// the same glyph and colour the rest of the app already uses for that
// state is the honest one here too.
export function CaveatNote({ title, children }) {
  return (
    <div className="caveat-note">
      <span className="caveat-note-glyph" aria-hidden="true">◑</span>
      <div>
        {title && <strong style={{ color: "var(--color-text)" }}>{title}</strong>}
        {title && <br />}
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- narrative */

// EXPLAIN's system prompt asks for plain prose, but real model output
// varies by provider -- Gemini returned clean prose, Groq's gpt-oss-120b
// returns real Markdown (headings, bold, pipe tables). Rather than trust
// one provider's current behaviour, or add a Markdown dependency for one
// consumer, this renders the block-level subset an officer-summary
// narrative actually uses, so raw **/###/| characters are never what an
// officer -- or a screenshot -- sees, whichever model answered.
function renderInline(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={`${keyPrefix}-${i}`}>{part.slice(1, -1)}</em>;
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

function parseNarrativeBlocks(text) {
  const lines = (text || "").split("\n");
  const blocks = [];
  let listBuf = [];
  let listKind = null;
  const flushList = () => {
    if (listBuf.length) blocks.push({ type: listKind, items: listBuf });
    listBuf = []; listKind = null;
  };
  const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

  for (let i = 0; i < lines.length;) {
    const trimmed = lines[i].trim();
    if (!trimmed) { flushList(); i += 1; continue; }
    if (/^#{1,6}\s+/.test(trimmed)) { flushList(); blocks.push({ type: "heading", text: trimmed.replace(/^#{1,6}\s+/, "") }); i += 1; continue; }
    if (/^-{3,}$/.test(trimmed)) { flushList(); blocks.push({ type: "hr" }); i += 1; continue; }
    if (/^[-*]\s+/.test(trimmed)) {
      if (listKind && listKind !== "ul") flushList();
      listKind = "ul"; listBuf.push(trimmed.replace(/^[-*]\s+/, ""));
      i += 1; continue;
    }
    if (/^\d+\.\s+/.test(trimmed)) {
      if (listKind && listKind !== "ol") flushList();
      listKind = "ol"; listBuf.push(trimmed.replace(/^\d+\.\s+/, ""));
      i += 1; continue;
    }
    if (trimmed.startsWith("|") && i + 1 < lines.length && /^\|?\s*-{2,}/.test(lines[i + 1].trim())) {
      flushList();
      const tableLines = [trimmed];
      let j = i + 1;
      while (j < lines.length && lines[j].trim().startsWith("|")) { tableLines.push(lines[j].trim()); j += 1; }
      blocks.push({ type: "table", header: cells(tableLines[0]), rows: tableLines.slice(2).map(cells) });
      i = j; continue;
    }
    flushList();
    blocks.push({ type: "p", text: trimmed });
    i += 1;
  }
  flushList();
  return blocks;
}

export function NarrativeText({ text }) {
  return (
    <div className="narrative">
      {parseNarrativeBlocks(text).map((b, i) => {
        if (b.type === "heading") return <h4 key={i}>{renderInline(b.text, `h${i}`)}</h4>;
        if (b.type === "hr") return <hr key={i} />;
        if (b.type === "ul" || b.type === "ol") {
          const ListTag = b.type;
          return <ListTag key={i}>{b.items.map((it, j) => <li key={j}>{renderInline(it, `li${i}-${j}`)}</li>)}</ListTag>;
        }
        if (b.type === "table") {
          return (
            <table key={i}>
              <thead><tr>{b.header.map((h, j) => <th key={j}>{h}</th>)}</tr></thead>
              <tbody>
                {b.rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci}>{renderInline(c, `t${i}-${ri}-${ci}`)}</td>)}</tr>)}
              </tbody>
            </table>
          );
        }
        return <p key={i}>{renderInline(b.text, `p${i}`)}</p>;
      })}
    </div>
  );
}

/* --------------------------------------------------------------- metrics */

export function Stat({ label, value, note, accent = "neutral" }) {
  return (
    <div className={`stat stat-accent-${accent}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value === null || value === undefined ? "—" : value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

// A metric is null, never zero, when nothing could be determined — an em
// dash says that plainly instead of looking like a real 0%.
export function MetricCard({ label, value, note }) {
  const shown = value === null || value === undefined ? "—" : `${Math.round(value)}%`;
  return (
    <div className="metric-card">
      <div className="metric-card-label">{label}</div>
      <div className="metric-card-value">{shown}</div>
      {note && <div className="metric-card-note">{note}</div>}
    </div>
  );
}

// Coverage: the unverified remainder is a visible hatch, never blank space.
export function CoverageMetric({ label, value, note }) {
  const determined = value !== null && value !== undefined;
  const pct = determined ? Math.max(0, Math.min(100, Math.round(value))) : 0;
  return (
    <div className="metric-card">
      <div className="metric-card-label">{label}</div>
      <div className="metric-card-value">{determined ? `${pct}%` : "—"}</div>
      <div className="meter-track">
        {determined && <div className="meter-fill" style={{ width: `${pct}%` }} />}
      </div>
      <div className="metric-card-note">
        {determined
          ? (pct < 100 ? `${100 - pct}% not independently verified` : "fully verified")
          : "not determined"}
        {note ? ` · ${note}` : ""}
      </div>
    </div>
  );
}

export function RiskBar({ low = 0, medium = 0, high = 0 }) {
  const total = low + medium + high;
  if (total === 0) return <p className="text-secondary text-sm">No bidders evaluated yet.</p>;
  const seg = (n, cls) => (n === 0 ? null : <div key={cls} className={`risk-bar-segment ${cls}`} style={{ width: `${(n / total) * 100}%` }} />);
  return (
    <div>
      <div className="risk-bar" role="img" aria-label={`Risk distribution: ${low} low, ${medium} medium, ${high} high`}>
        {seg(low, "risk-bar-low")}
        {seg(medium, "risk-bar-medium")}
        {seg(high, "risk-bar-high")}
      </div>
      <p className="text-secondary text-xs" style={{ marginTop: 8 }}>
        <span className="mono">{low}</span> low · <span className="mono">{medium}</span> medium ·{" "}
        <span className="mono">{high}</span> high · <span className="mono">{total}</span> total
      </p>
    </div>
  );
}

/* ----------------------------------------------------------------- chain */

// The evidence chain, rendered explicitly: Requirement → Document → Page →
// Extracted value → Verification → Rule → Verdict. This is the product's
// central claim made visible — never a summary that hides its own trace.
export function EvidenceChain({ steps }) {
  return (
    <div className="chain">
      {steps.map((s, i) => (
        <div key={s.label + i}>
          <div className="chain-step">
            <div className="chain-step-label">{s.label}</div>
            <div className="chain-step-value">{s.value}</div>
          </div>
          {i < steps.length - 1 && <div className="chain-arrow" aria-hidden="true">↓</div>}
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- drawer */

export function Drawer({ open, title, subtitle, onClose, children }) {
  if (!open) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}
             onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h2 className="section-title">{title}</h2>
            {subtitle && <p className="text-secondary text-sm" style={{ marginTop: 4 }}>{subtitle}</p>}
          </div>
          <button type="button" className="btn btn-sm btn-secondary" onClick={onClose}>Close</button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

/* ---------------------------------------------------------------- dialog */

export function ConfirmDialog({ open, title, body, confirmLabel = "Confirm", danger, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header"><h2 className="section-title">{title}</h2></div>
        <div className="dialog-body">{body}</div>
        <div className="dialog-footer">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="button" className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ misc */

export function LinkButton({ to, children, variant = "secondary", size }) {
  return (
    <Link to={to} className={`btn btn-${variant}${size === "sm" ? " btn-sm" : ""}`}>{children}</Link>
  );
}

export function Dash() {
  return <span className="text-muted">—</span>;
}
