import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { roleAtLeast, useAuth } from "./authContext";
import { useToast } from "./notifications";
import "./appShell.css";

// The application shell -- a left sidebar for every authenticated page,
// replacing the old single top nav bar (round 5 frontend audit). Every nav
// item below maps to a route that genuinely exists and does something real;
// none of these are aspirational labels for functionality that isn't built
// yet ("Documents", "Verification", "Compliance", and "Evidence" as
// standalone sections were explicitly asked for in the brief this shell was
// built against, but none of them exist as their own page today -- they
// live inside a tender's or a bidder's own page instead, so they're not
// listed here as if they were separate places to go).
const NAV_ITEMS = [
  { to: "/dashboard", label: "Mission Control", icon: "▣" },
  { to: "/tenders", label: "Tenders", icon: "▤" },
  { to: "/register", label: "Register Bidder", icon: "➕" },
  { to: "/audit", label: "Audit Trail", icon: "≣" },
];

const ADMIN_NAV_ITEM = { to: "/admin/users", label: "Officer Accounts", icon: "⚭" };

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("satyapramana-theme") || "system";
    } catch {
      return "system";
    }
  });
  function apply(next) {
    setTheme(next);
    if (next === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("satyapramana-theme", next);
    } catch {
      // Private browsing / storage blocked -- the toggle still works for
      // this page view, it just won't persist.
    }
  }
  return [theme, apply];
}

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = { system: "light", light: "dark", dark: "system" };
  const label = { system: "System", light: "Light", dark: "Dark" };
  return (
    <button type="button" className="shell-theme-toggle" onClick={() => setTheme(next[theme])}>
      Theme: {label[theme]}
    </button>
  );
}

// The one piece of "current context" this shell can honestly show: which
// tender or bidder the URL is currently scoped to, read directly from the
// route params already in the URL -- never a second fetch just to populate
// a breadcrumb, and never a global search box, since no endpoint exists to
// search across tenders/bidders yet (adding one here would be exactly the
// "navigation for functionality that doesn't exist" the brief warned against).
function useTopBarContext() {
  const location = useLocation();
  const tenderMatch = location.pathname.match(/^\/tenders\/([^/]+)/);
  const bidderMatch = location.pathname.match(/^\/bidders\/([^/]+)/);
  if (tenderMatch) return { kind: "Tender", id: decodeURIComponent(tenderMatch[1]) };
  if (bidderMatch) {
    const params = new URLSearchParams(location.search);
    const tenderId = params.get("tender_id");
    return { kind: "Bidder", id: decodeURIComponent(bidderMatch[1]), tenderId };
  }
  return null;
}

export default function AppShell({ children }) {
  const { session, logout } = useAuth();
  const { notify } = useToast();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const context = useTopBarContext();

  if (!session) {
    // Signed out: no sidebar to navigate with (there's nowhere to go), just
    // a minimal header and the page itself (StatusPage or LoginPage).
    return (
      <div className="shell-signed-out">
        <header className="shell-signed-out-header">
          <span className="shell-brand">
            <span className="shell-brand-name">SATYAPRAMĀṆ</span>
            <span className="shell-brand-sub">Tender Compliance</span>
          </span>
          <span className="shell-trust-note">Real data only — no simulated authority response</span>
          <Link to="/login" className="shell-signin-link">Sign in →</Link>
        </header>
        <main className="shell-signed-out-main">{children}</main>
      </div>
    );
  }

  function onSignOut() {
    logout();
    notify("Signed out.", { kind: "info" });
  }

  const navItems = roleAtLeast(session.role, "ADMIN") ? [...NAV_ITEMS, ADMIN_NAV_ITEM] : NAV_ITEMS;

  return (
    <div className="shell">
      <button type="button" className="shell-mobile-toggle" onClick={() => setMobileOpen((v) => !v)}
              aria-expanded={mobileOpen} aria-controls="shell-sidebar">
        <span aria-hidden="true">☰</span> Menu
      </button>

      <aside id="shell-sidebar" className={`shell-sidebar${mobileOpen ? " shell-sidebar-open" : ""}`}>
        <div className="shell-brand">
          <span className="shell-brand-name">SATYAPRAMĀṆ</span>
          <span className="shell-brand-sub">Tender Compliance</span>
        </div>
        <p className="shell-trust-note shell-trust-note-sidebar">Real data only — no simulated authority response</p>

        <nav className="shell-nav" onClick={() => setMobileOpen(false)}>
          {navItems.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`shell-nav-item${location.pathname === item.to ? " shell-nav-item-active" : ""}`}
            >
              <span className="shell-nav-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </Link>
          ))}
          <Link to="/" className={`shell-nav-item${location.pathname === "/" ? " shell-nav-item-active" : ""}`}>
            <span className="shell-nav-icon" aria-hidden="true">&#9432;</span>
            Verification Status
          </Link>
        </nav>

        <div className="shell-sidebar-footer">
          <ThemeToggle />
          <div className="shell-account">
            <span className="shell-account-name mono">{session.displayName}</span>
            <span className="shell-account-role">{session.role.replace("_", " ")}</span>
          </div>
          <button type="button" className="shell-signout" onClick={onSignOut}>Sign out</button>
        </div>
      </aside>

      {mobileOpen && <div className="shell-mobile-backdrop" onClick={() => setMobileOpen(false)} />}

      <div className="shell-body">
        {context && (
          <div className="shell-topbar">
            <span className="shell-topbar-crumb">
              {context.kind}: <span className="mono">{context.id}</span>
              {context.tenderId && <> &middot; Tender: <span className="mono">{context.tenderId}</span></>}
            </span>
          </div>
        )}
        <main className="shell-main">{children}</main>
      </div>
    </div>
  );
}
