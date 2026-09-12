import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getCapabilities, listTenders } from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { useToast } from "../notifications";

// The shell: a fixed navy sidebar, a quiet top bar, and the working area.
// Every nav entry below resolves to a real page backed by real endpoints —
// nothing here is a label for functionality that doesn't exist.
const NAV = [
  { to: "/dashboard", label: "Mission Control", glyph: "▦" },
  { to: "/tenders", label: "Tenders", glyph: "▤" },
  { to: "/bidders", label: "Bidders", glyph: "⚏" },
  { to: "/review", label: "Review queue", glyph: "☑" },
  { to: "/documents", label: "Documents", glyph: "▥" },
  { to: "/verification", label: "Verification", glyph: "⛉" },
  { to: "/compliance", label: "Compliance", glyph: "✓" },
  { to: "/evidence", label: "Evidence", glyph: "⌕" },
  { to: "/reports", label: "Reports", glyph: "▣" },
  { to: "/audit", label: "Audit Trail", glyph: "≣" },
];

function initials(name) {
  if (!name) return "?";
  return name.trim().slice(0, 2).toUpperCase();
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem("satyapramana-theme") || "system"; } catch { return "system"; }
  });
  function apply(next) {
    setTheme(next);
    if (next === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try { localStorage.setItem("satyapramana-theme", next); } catch { /* storage blocked */ }
  }
  return [theme, apply];
}

// Global search over the tender list the session has already loaded — a
// real client-side filter over real records, never a fabricated "smart
// search" hitting an endpoint that doesn't exist.
function GlobalSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [tenders, setTenders] = useState([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    listTenders().then((b) => setTenders(b.tenders || [])).catch(() => setTenders([]));
  }, []);

  useEffect(() => {
    function onClickAway(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, []);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return tenders.filter((t) => t.toLowerCase().includes(q)).slice(0, 8);
  }, [query, tenders]);

  function go(tenderId) {
    setQuery("");
    setOpen(false);
    navigate(`/tenders/${encodeURIComponent(tenderId)}`);
  }

  return (
    <div className="topbar-search" ref={boxRef}>
      <span className="topbar-search-glyph" aria-hidden="true">⌕</span>
      <input
        type="search"
        value={query}
        placeholder="Search tenders by ID…"
        aria-label="Search tenders by ID"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) go(matches[0]); if (e.key === "Escape") setOpen(false); }}
      />
      {open && query.trim() && (
        <div className="topbar-results">
          {matches.length === 0 ? (
            <p className="topbar-result-empty">No tender ID matches “{query}”.</p>
          ) : (
            matches.map((t) => (
              <button key={t} type="button" className="topbar-result" onClick={() => go(t)}>
                <span aria-hidden="true">▤</span>
                <span className="mono">{t}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// Notifications are derived from real system state — capabilities that
// aren't live, and nothing else invented. An empty list stays empty rather
// than being padded with decorative activity.
function Notifications() {
  const [alerts, setAlerts] = useState([]);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    getCapabilities()
      .then((body) => {
        const rows = body.capabilities || [];
        setAlerts(
          rows
            .filter((c) => c.status !== "LIVE")
            .map((c) => ({
              id: c.adapter_id,
              title: c.capability_id || c.authority,
              detail: c.status === "AWAITING_CREDENTIALS"
                ? "Awaiting credentials — every check against this authority returns UNKNOWN with a stated reason."
                : (c.detail || "No lawful programmatic source available."),
              status: c.status,
            }))
        );
      })
      .catch(() => setAlerts([]));
  }, []);

  useEffect(() => {
    function onClickAway(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, []);

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button type="button" className="topbar-button" onClick={() => setOpen((v) => !v)}
              aria-label={`Verification alerts (${alerts.length})`} aria-expanded={open}>
        <span aria-hidden="true">◔</span>
        {alerts.length > 0 && <span className="topbar-badge-count">{alerts.length}</span>}
      </button>
      {open && (
        <div className="popover">
          <div className="popover-header">Verification alerts</div>
          <div className="popover-body">
            {alerts.length === 0 ? (
              <p className="popover-empty">Every registered capability is live.</p>
            ) : (
              alerts.map((a) => (
                <div key={a.id} className="popover-item">
                  <span aria-hidden="true" style={{ color: "var(--status-partial-fg)" }}>◑</span>
                  <div>
                    <div style={{ fontWeight: 600 }}>{a.title}</div>
                    <div className="text-secondary text-xs" style={{ marginTop: 2 }}>{a.detail}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ProfileMenu() {
  const { session, logout } = useAuth();
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  const ref = useRef(null);

  useEffect(() => {
    function onClickAway(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, []);

  const nextTheme = { system: "light", light: "dark", dark: "system" };
  const themeLabel = { system: "System", light: "Light", dark: "Dark" };

  return (
    <div className="topbar-profile" ref={ref}>
      <button type="button" className="topbar-profile-trigger" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="topbar-avatar" aria-hidden="true">{initials(session.displayName)}</span>
        <span className="text-sm">{session.displayName}</span>
        <span aria-hidden="true" className="text-muted">▾</span>
      </button>
      {open && (
        <div className="popover" style={{ width: 240 }}>
          <div className="popover-header">
            {session.displayName}
            <div className="text-xs text-muted" style={{ fontWeight: 500, marginTop: 2 }}>
              {session.role.replace("_", " ")}
            </div>
          </div>
          <div className="popover-body">
            <div className="popover-item" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <span>Theme</span>
              <button type="button" className="btn btn-sm btn-secondary" onClick={() => setTheme(nextTheme[theme])}>
                {themeLabel[theme]}
              </button>
            </div>
            {roleAtLeast(session.role, "ADMIN") && (
              <Link to="/settings" className="popover-item" onClick={() => setOpen(false)} style={{ textDecoration: "none", color: "inherit" }}>
                <span aria-hidden="true">⚙</span> Settings & officer accounts
              </Link>
            )}
            <button type="button" className="popover-item"
                    style={{ width: "100%", background: "none", border: "none", cursor: "pointer", font: "inherit", textAlign: "left" }}
                    onClick={() => { logout(); notify("Signed out.", { kind: "info" }); }}>
              <span aria-hidden="true">⇥</span> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// The one piece of context the shell can state honestly: which tender or
// bidder the current URL is scoped to, read straight from the route.
function ContextChip() {
  const { pathname, search } = useLocation();
  const tender = pathname.match(/^\/tenders\/([^/]+)/);
  const bidder = pathname.match(/^\/bidders\/([^/]+)/);
  if (tender) {
    return (
      <span className="topbar-context">
        <span className="topbar-context-label">Tender</span>
        <span className="mono truncate">{decodeURIComponent(tender[1])}</span>
      </span>
    );
  }
  if (bidder) {
    const tid = new URLSearchParams(search).get("tender_id");
    return (
      <span className="topbar-context">
        <span className="topbar-context-label">Bidder</span>
        <span className="mono truncate">{decodeURIComponent(bidder[1])}</span>
        {tid && <><span className="text-muted">·</span><span className="mono truncate">{tid}</span></>}
      </span>
    );
  }
  return null;
}

export default function AppShell({ children }) {
  const { session, logout } = useAuth();
  const { notify } = useToast();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!session) {
    return (
      <div className="signed-out">
        <header className="signed-out-header">
          <Link to="/" className="sidebar-brand">
            <span className="sidebar-brand-mark">SATYAPRAMĀṆ</span>
            <span className="sidebar-brand-sub">Tender Compliance Platform</span>
          </Link>
          <span className="signed-out-note">Every verdict traced to evidence, an authority and a rule version</span>
        </header>
        <main id="main">{children}</main>
      </div>
    );
  }

  const nav = roleAtLeast(session.role, "ADMIN")
    ? [...NAV, { to: "/settings", label: "Settings", glyph: "⚙" }]
    : NAV;

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>

      <aside className={`sidebar${mobileOpen ? " sidebar-open" : ""}`} id="sidebar">
        <Link to="/dashboard" className="sidebar-brand">
          <span className="sidebar-brand-mark">SATYAPRAMĀṆ</span>
          <span className="sidebar-brand-sub">Tender Compliance Platform</span>
        </Link>

        <nav className="sidebar-nav" aria-label="Main" onClick={() => setMobileOpen(false)}>
          {nav.map((item) => {
            const active = location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
            return (
              <Link key={item.to} to={item.to} className={`sidebar-link${active ? " sidebar-link-active" : ""}`}
                    aria-current={active ? "page" : undefined}>
                <span className="sidebar-icon" aria-hidden="true">{item.glyph}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="sidebar-avatar" aria-hidden="true">{initials(session.displayName)}</span>
            <span className="sidebar-user-text">
              <span className="sidebar-user-name">{session.displayName}</span>
              <span className="sidebar-user-role">{session.role.replace("_", " ")}</span>
            </span>
          </div>
          <button type="button" className="sidebar-action"
                  onClick={() => { logout(); notify("Signed out.", { kind: "info" }); }}>
            <span className="sidebar-icon" aria-hidden="true">⇥</span> Sign out
          </button>
        </div>
      </aside>

      {mobileOpen && <div className="shell-scrim" onClick={() => setMobileOpen(false)} />}

      <div className="shell-body">
        <header className="topbar">
          <button type="button" className="shell-mobile-toggle" onClick={() => setMobileOpen((v) => !v)}
                  aria-label="Toggle navigation" aria-controls="sidebar" aria-expanded={mobileOpen}>
            <span aria-hidden="true">☰</span>
          </button>
          <GlobalSearch />
          <ContextChip />
          <div className="topbar-right">
            <Notifications />
            <ProfileMenu />
          </div>
        </header>
        <main className="shell-main" id="main">{children}</main>
      </div>
    </div>
  );
}
