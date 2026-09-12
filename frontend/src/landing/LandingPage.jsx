import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getCapabilities } from "../api";
import { useApi } from "../lib/useApi";
import { useTheme } from "../lib/useTheme";
import { AshokaChakra, EmblemRoundel, Icon, IndianFlag } from "./Emblems";
import Pipeline from "./Pipeline";
import "./landing.css";

// The public front door. Signed-out visitors only — App.jsx sends any live
// session straight to its own portal. Everything stated here is true of
// the deployment behind it: the authority strip reads GET /capabilities
// live, and nothing below claims a number the system doesn't have.

const STATUS_LABEL = {
  LIVE: "Live",
  AWAITING_CREDENTIALS: "Awaiting credentials",
  UNAVAILABLE: "No lawful source",
};
const STATUS_ORDER = { LIVE: 0, AWAITING_CREDENTIALS: 1, UNAVAILABLE: 2 };
const byStatus = (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);

const STEPS = [
  { icon: "user", title: "Register the bidder", actor: "Officer",
    text: "A bidder exists in the context of one tender. Optional common-entity attributes (director, address, phone, bank account) are hashed with a salt — the raw value never enters the log — and matched across bidders." },
  { icon: "upload", title: "Upload documents", actor: "Officer or bidder",
    text: "GST, PAN, CIN and Udyam certificates as PDFs. Each file is hashed and stored by content, so the same document can never be recorded twice as two things." },
  { icon: "scan", title: "Extract, deterministically", actor: "System",
    text: "Identifiers are located by grammar in the real text layer and structurally validated — check digits, embedded PAN, format. Every field keeps its page and region." },
  { icon: "shield", title: "Verify against the authority", actor: "System",
    text: "PAN, GST and CIN are checked live. An unreachable authority yields UNKNOWN with the reason, and stays visible in coverage instead of disappearing." },
  { icon: "stamp", title: "Officer decides", actor: "Officer",
    text: "The review queue shows every bidder awaiting a decision, with the exact result view the bidder will see. QUALIFY or DISQUALIFY is recorded as an event on the chain." },
];

const VERDICTS = [
  { id: "PASS", glyph: "✓", text: "The evidence satisfies the requirement." },
  { id: "FAIL", glyph: "✕", text: "The evidence contradicts the requirement." },
  { id: "PARTIAL", glyph: "◑", text: "Some, not all, of what the requirement needs is established." },
  { id: "UNKNOWN", glyph: "?", text: "The evidence needed isn't available — stated with a reason, never guessed." },
];

const PRINCIPLES = [
  { icon: "ban", title: "Nothing is simulated",
    text: "No mock, sample or placeholder data exists anywhere in the system. Where an authority can't be reached the answer is UNKNOWN with a machine-readable reason." },
  { icon: "cpu", title: "AI proposes, code decides",
    text: "A model may suggest a reading or a linkage. Only deterministic code and a named human officer ever decide, and an identifier match always beats semantic similarity." },
  { icon: "chain", title: "Append-only, hash-chained",
    text: "Every state change is an event carrying the SHA-256 of the one before it. Nothing is edited or deleted; the whole chain is re-verifiable from the audit page at any time." },
  { icon: "crosshair", title: "Provenance to the pixel",
    text: "Every extracted field carries its page and region through to the screen. Click a verdict and you land on the exact line of the source PDF that produced it." },
];

const ROLES = [
  { tier: "Role 0", title: "Bidder", points: ["Sees the tenders they're registered on", "Reads each tender's adopted requirements", "Submits documents in a guided three-step flow", "Sees the officer's recorded result — nothing before it"] },
  { tier: "Role 1", title: "Officer", points: ["Registers bidders and uploads documents", "Runs verification and reads the evidence", "Works the review queue", "Records QUALIFY / DISQUALIFY"] },
  { tier: "Role 2", title: "Senior officer", points: ["Everything an officer can", "Adopts a tender's rule pack", "Records an override with a stated reason"] },
  { tier: "Role 3", title: "Administrator", points: ["Everything a senior officer can", "Provisions every account — there is no self-signup", "Assigns bidder accounts to registered bidders"] },
];

function useScrollReveal(rootRef) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root || !("IntersectionObserver" in window)) return undefined;
    root.classList.add("js-reveal");
    const targets = root.querySelectorAll(".lp-reveal");
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) { entry.target.classList.add("is-in"); io.unobserve(entry.target); }
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, [rootRef]);
}

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = { system: "light", light: "dark", dark: "system" };
  const icon = { system: "monitor", light: "sun", dark: "moon" };
  const label = { system: "System theme", light: "Light theme", dark: "Dark theme" };
  return (
    <button type="button" className="lp-utility-btn" onClick={() => setTheme(next[theme])}
            aria-label={`${label[theme]} — switch`} title={label[theme]}>
      <Icon name={icon[theme]} size={15} /> <span>{label[theme].replace(" theme", "")}</span>
    </button>
  );
}

function AuthorityPills({ caps }) {
  if (caps.loading) return <p className="lp-live-note" aria-live="polite">Checking which authorities are reachable…</p>;
  if (caps.error || !caps.data) {
    return <p className="lp-live-note">The verification service could not be reached just now, so no authority status is shown.</p>;
  }
  const rows = caps.data.capabilities.filter((c) => c.capability_id).sort(byStatus);
  return (
    <ul className="lp-live-pills" aria-label="Verification authorities">
      {rows.map((c) => (
        <li key={c.adapter_id} className={`lp-pill lp-pill-${c.status.toLowerCase()}`}>
          <span className="lp-pill-dot" aria-hidden="true" />
          {c.capability_id.replace("_STATUS", "")}
          <span className="lp-pill-state">{STATUS_LABEL[c.status] || c.status}</span>
        </li>
      ))}
    </ul>
  );
}

function AuthorityTable({ caps }) {
  if (caps.loading) return <p className="lp-live-note">Loading the live capability registry…</p>;
  if (caps.error || !caps.data) return <p className="lp-live-note">Registry unavailable right now — nothing is shown in its place.</p>;
  return (
    <div className="lp-table-wrap">
      <table className="lp-table">
        <thead>
          <tr><th>Authority</th><th>Capability</th><th>Status</th><th>Note</th></tr>
        </thead>
        <tbody>
          {[...caps.data.capabilities].sort(byStatus).map((c) => (
            <tr key={c.adapter_id}>
              <td className="lp-td-strong">{c.authority}</td>
              <td className="mono">{c.capability_id || "—"}</td>
              <td>
                <span className={`lp-status lp-status-${c.status.toLowerCase()}`}>
                  <span className="lp-pill-dot" aria-hidden="true" />{STATUS_LABEL[c.status] || c.status}
                </span>
              </td>
              <td className="text-secondary">
                {c.detail || (c.status === "LIVE"
                  ? `Tier ${c.tier} · ${c.channel.toLowerCase()} channel · answered on every verification run`
                  : `Tier ${c.tier} · ${c.channel.toLowerCase()} channel · no configured source yet, so every check returns UNKNOWN with a stated reason`)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function LandingPage() {
  const rootRef = useRef(null);
  const headerRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const caps = useApi(getCapabilities, []);
  useScrollReveal(rootRef);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return undefined;
    function onScroll() { el.classList.toggle("is-scrolled", window.scrollY > 8); }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const liveCount = caps.data?.live_count;

  return (
    <div className="landing" ref={rootRef}>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="lp-ribbon" aria-hidden="true"><span /><span /><span /></div>

      <div className="lp-utility">
        <div className="lp-wrap lp-utility-inner">
          <span className="lp-utility-left">
            <IndianFlag height={14} className="lp-flag" />
            <span>Smart India Hackathon 2026 <span className="lp-lbl-long">· Problem statement SIH26100 · prototype</span></span>
          </span>
          <ThemeToggle />
        </div>
      </div>

      <header className="lp-header" ref={headerRef}>
        <div className="lp-wrap lp-header-inner">
          <a className="lp-brand" href="#top">
            <EmblemRoundel size={44} className="lp-emblem" />
            <span className="lp-brand-text">
              <span className="lp-brand-devanagari" lang="hi">सत्यप्रमाण</span>
              <span className="lp-brand-latin">Satyapramāṇ · Tender compliance</span>
            </span>
          </a>
          <nav className={`lp-nav${menuOpen ? " is-open" : ""}`} id="lp-nav" aria-label="Sections" onClick={() => setMenuOpen(false)}>
            <a href="#how">How it works</a>
            <a href="#authorities">Authorities</a>
            <a href="#principles">Principles</a>
            <a href="#roles">Who uses it</a>
          </nav>
          <div className="lp-header-actions">
            <Link to="/login" className="btn btn-primary">Sign in</Link>
            <button type="button" className="lp-menu-btn btn btn-secondary btn-icon" aria-controls="lp-nav"
                    aria-expanded={menuOpen} aria-label="Toggle sections menu" onClick={() => setMenuOpen((v) => !v)}>
              <Icon name={menuOpen ? "close" : "menu"} size={18} />
            </button>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="lp-hero" id="top">
          <AshokaChakra className="lp-hero-chakra" size={720} />
          <div className="lp-wrap lp-hero-grid">
            <div className="lp-hero-copy">
              <p className="lp-eyebrow"><span className="lp-tricolor-dot" aria-hidden="true" /> Bid compliance verification for public procurement</p>
              <h1>Every verdict traced to <em>evidence</em>, an <em>authority</em> and a <em>rule version</em>.</h1>
              <p className="lp-hero-sub">
                Satyapramāṇ reads a bidder's statutory documents deterministically, checks each identifier with the
                issuing authority live, evaluates the tender's adopted rule pack, and leaves the decision to a procuring
                officer — with every step on an append-only, hash-chained audit log.
              </p>
              <div className="lp-hero-ctas">
                <Link to="/login" className="btn btn-primary btn-lg">Officer sign-in</Link>
                <Link to="/login" className="btn btn-secondary btn-lg">Bidder portal</Link>
                <a href="#how" className="lp-link-arrow">See how a document is checked <Icon name="arrow" size={16} /></a>
              </div>
              <div className="lp-live">
                <p className="lp-live-title">
                  Authorities on this deployment
                  {typeof liveCount === "number" && <span className="lp-live-count"> · {liveCount} live</span>}
                </p>
                <AuthorityPills caps={caps} />
              </div>
            </div>
            <div className="lp-hero-visual">
              <Pipeline />
            </div>
          </div>
        </section>

        <section className="lp-verdicts" aria-labelledby="lp-verdicts-h">
          <div className="lp-wrap">
            <h2 id="lp-verdicts-h" className="lp-visually-hidden">The four verdicts</h2>
            <div className="lp-verdict-grid">
              {VERDICTS.map((v, i) => (
                <div key={v.id} className={`lp-verdict lp-verdict-${v.id.toLowerCase()} lp-reveal`} data-delay={i}>
                  <span className="lp-verdict-glyph" aria-hidden="true">{v.glyph}</span>
                  <div>
                    <h3 className="mono">{v.id}</h3>
                    <p>{v.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-section" id="how" aria-labelledby="lp-how-h">
          <div className="lp-wrap">
            <div className="lp-section-head lp-reveal">
              <p className="lp-eyebrow">How it works</p>
              <h2 id="lp-how-h">Five stages. One officer. No shortcuts.</h2>
              <p>The order below is the order the orchestrator runs — a stage never proceeds on a guess about the one before it.</p>
            </div>
            <ol className="lp-steps">
              {STEPS.map((s, i) => (
                <li key={s.title} className="lp-step lp-reveal" data-delay={i}>
                  <span className="lp-step-num mono">0{i + 1}</span>
                  <span className="lp-step-icon"><Icon name={s.icon} size={20} /></span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                  <span className="lp-step-actor">{s.actor}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="lp-section lp-section-alt" id="authorities" aria-labelledby="lp-auth-h">
          <div className="lp-wrap">
            <div className="lp-section-head lp-reveal">
              <p className="lp-eyebrow">Live capability registry</p>
              <h2 id="lp-auth-h">What this deployment can verify — and what it honestly can't.</h2>
              <p>This table is read from the running service, not written here. A missing integration is a registered adapter that says so, not a row that quietly doesn't exist.</p>
            </div>
            <div className="lp-reveal"><AuthorityTable caps={caps} /></div>
          </div>
        </section>

        <section className="lp-section" id="principles" aria-labelledby="lp-prin-h">
          <div className="lp-wrap">
            <div className="lp-section-head lp-reveal">
              <p className="lp-eyebrow">Design charter</p>
              <h2 id="lp-prin-h">Built to be trusted by someone who has to defend the decision.</h2>
            </div>
            <div className="lp-principles">
              {PRINCIPLES.map((p, i) => (
                <article key={p.title} className="lp-principle lp-reveal" data-delay={i}>
                  <span className="lp-principle-icon"><Icon name={p.icon} size={22} /></span>
                  <h3>{p.title}</h3>
                  <p>{p.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-section lp-section-alt" id="roles" aria-labelledby="lp-roles-h">
          <div className="lp-wrap">
            <div className="lp-section-head lp-reveal">
              <p className="lp-eyebrow">Who uses it</p>
              <h2 id="lp-roles-h">Four roles, totally ordered. Every action recorded against a named identity.</h2>
              <p>Accounts are provisioned by an administrator. There is no self-registration, no OTP flow and no social sign-in — by design.</p>
            </div>
            <div className="lp-roles">
              {ROLES.map((r, i) => (
                <article key={r.title} className="lp-role lp-reveal" data-delay={i}>
                  <span className="lp-role-tier">{r.tier}</span>
                  <h3>{r.title}</h3>
                  <ul>{r.points.map((pt) => <li key={pt}>{pt}</li>)}</ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-cta">
          <div className="lp-wrap">
            <div className="lp-cta-inner lp-reveal">
              <AshokaChakra className="lp-cta-chakra" size={320} />
              <div>
                <h2>Sign in to the workspace your role gets.</h2>
                <p>Officers land on Mission Control and the review queue. Bidders land on their portal: tenders, requirements, submissions and results. Same sign-in, different door.</p>
              </div>
              <Link to="/login" className="btn btn-primary btn-lg">Sign in <Icon name="arrow" size={16} /></Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap">
          <div className="lp-footer-grid">
            <div>
              <div className="lp-brand" style={{ marginBottom: 12 }}>
                <EmblemRoundel size={36} className="lp-emblem" />
                <span className="lp-brand-text">
                  <span className="lp-brand-devanagari" lang="hi">सत्यप्रमाण</span>
                  <span className="lp-brand-latin">Satyapramāṇ</span>
                </span>
              </div>
              <p>A tender compliance verification platform: deterministic extraction, live authority checks, a four-state verdict algebra, and an append-only audit log.</p>
            </div>
            <div>
              <h4>On this page</h4>
              <ul>
                <li><a href="#how">How it works</a></li>
                <li><a href="#authorities">Authorities</a></li>
                <li><a href="#principles">Principles</a></li>
                <li><a href="#roles">Who uses it</a></li>
              </ul>
            </div>
            <div>
              <h4>Sign in</h4>
              <ul>
                <li><Link to="/login">Officer sign-in</Link></li>
                <li><Link to="/login">Bidder portal</Link></li>
              </ul>
            </div>
          </div>
          <div className="lp-footer-legal">
            <span>
              Prototype built for Smart India Hackathon 2026 (SIH26100). Not an official service of the Government of India
              or of the Government e-Marketplace (GeM), and not affiliated with or endorsed by either. The national flag and
              Ashoka Chakra are displayed with respect, per the Flag Code of India.
            </span>
            <IndianFlag height={18} className="lp-flag" />
          </div>
        </div>
        <div className="lp-ribbon" aria-hidden="true"><span /><span /><span /></div>
      </footer>
    </div>
  );
}
