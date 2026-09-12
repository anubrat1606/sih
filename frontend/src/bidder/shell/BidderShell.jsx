import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../authContext";
import { useApi } from "../../lib/useApi";
import { useToast } from "../../notifications";
import { deriveNotifications, loadNotificationSource } from "../notifications/deriveNotifications";
import { NotificationBell } from "../notifications/NotificationBell";

// The bidder-facing shell. Deliberately the same structural primitives as
// the officer shell (shell/AppShell.jsx) -- sidebar, topbar, shell-main --
// from design/shell.css, unchanged: one visual language for the whole
// product, not a second one invented for this side. The .bidder-portal
// class is the scoping hook Kevin's responsive.css (round 6, K3) targets.
const NAV = [
  { to: "/portal", label: "Dashboard", glyph: "▦" },
  { to: "/portal/tenders", label: "Tenders", glyph: "▤" },
  { to: "/portal/submissions", label: "My submissions", glyph: "⚏" },
  { to: "/portal/results", label: "My results", glyph: "✓" },
  { to: "/portal/notifications", label: "Notifications", glyph: "◔" },
  { to: "/portal/profile", label: "Profile", glyph: "◑" },
  { to: "/portal/help", label: "Help", glyph: "?" },
];

function initials(name) {
  if (!name) return "?";
  return name.trim().slice(0, 2).toUpperCase();
}

/**
 * @param {{children: React.ReactNode, breadcrumbs?: {label: string, to?: string}[]}} props
 * `breadcrumbs` is optional per-page trail (e.g. Tenders › BHEL-T7J1Z68239)
 * -- pages that don't pass one just render Home.
 */
export default function BidderShell({ children, breadcrumbs }) {
  const { session, logout } = useAuth();
  const { notify } = useToast();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Fetched once per shell mount, not per page -- the bell needs a live
  // count on every bidder page, not just NotificationsPage.jsx (which
  // fetches the same source itself when actually opened, since navigating
  // there is a real page load with its own loading/error state; this is
  // just for the ambient badge count elsewhere).
  const source = useApi(loadNotificationSource, []);
  const notifications = source.data
    ? deriveNotifications(source.data.myTenders, source.data.submissionsByTender, source.data.resultsByTender)
    : [];

  const trail = breadcrumbs?.length ? breadcrumbs : [{ label: "Home", to: "/portal" }];

  return (
    <div className="shell bidder-portal">
      <a className="skip-link" href="#main">Skip to content</a>

      <aside className={`sidebar${mobileOpen ? " sidebar-open" : ""}`} id="bidder-sidebar">
        <Link to="/portal" className="sidebar-brand">
          <span className="sidebar-brand-mark">SATYAPRAMĀṆ</span>
          <span className="sidebar-brand-sub">Bidder Portal</span>
        </Link>

        <nav className="sidebar-nav" aria-label="Bidder" onClick={() => setMobileOpen(false)}>
          {NAV.map((item) => {
            const active = location.pathname === item.to
              || (item.to !== "/portal" && location.pathname.startsWith(`${item.to}/`));
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
            <span className="sidebar-avatar" aria-hidden="true">{initials(session?.displayName)}</span>
            <span className="sidebar-user-text">
              <span className="sidebar-user-name">{session?.displayName}</span>
              <span className="sidebar-user-role">Bidder</span>
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
                  aria-label="Toggle navigation" aria-controls="bidder-sidebar" aria-expanded={mobileOpen}>
            <span aria-hidden="true">☰</span>
          </button>
          <nav className="bidder-breadcrumbs" aria-label="Breadcrumb">
            {trail.map((crumb, i) => (
              <span key={crumb.label}>
                {i > 0 && <span aria-hidden="true"> › </span>}
                {crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}
              </span>
            ))}
          </nav>
          <div className="topbar-right">
            <NotificationBell notifications={notifications} />
          </div>
        </header>

        <main id="main" className="shell-main">{children}</main>

        <footer className="bidder-footer">
          <Link to="/portal/help">Help</Link>
          <span aria-hidden="true"> · </span>
          <a href="/">Officer sign-in</a>
        </footer>
      </div>
    </div>
  );
}
