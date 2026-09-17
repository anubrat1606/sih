import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { roleAtLeast, useAuth } from "../../authContext";
import { useTheme } from "../../lib/useTheme";
import { useToast } from "../../notifications";

// The admin console: a third shell, structurally the same primitives as
// the officer and bidder shells (sidebar / topbar / shell-main from
// design/shell.css) so nothing here invents a second visual language --
// only .admin-console (admin.css) marks it as its own surface, the same
// scoping pattern bidder-portal already uses for its own responsive CSS.
const NAV = [
  { to: "/admin", label: "Overview", glyph: "▦" },
  { to: "/admin/accounts", label: "Accounts", glyph: "◑" },
  { to: "/admin/audit", label: "Audit & System", glyph: "≣" },
];

function initials(name) {
  if (!name) return "?";
  return name.trim().slice(0, 2).toUpperCase();
}

export default function AdminShell({ children, breadcrumbs }) {
  const { session, logout } = useAuth();
  const { notify } = useToast();
  const location = useLocation();
  const [theme, setTheme] = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const nextTheme = { system: "light", light: "dark", dark: "system" };
  const trail = breadcrumbs?.length ? breadcrumbs : [{ label: "Admin console" }];

  return (
    <div className="shell admin-console">
      <a className="skip-link" href="#main">Skip to content</a>

      <aside className={`sidebar${mobileOpen ? " sidebar-open" : ""}`} id="admin-sidebar">
        <Link to="/admin" className="sidebar-brand">
          <span className="sidebar-brand-mark">SATYAPRAMĀṆ</span>
          <span className="sidebar-brand-sub">Admin Console</span>
        </Link>

        <nav className="sidebar-nav" aria-label="Admin" onClick={() => setMobileOpen(false)}>
          {NAV.map((item) => {
            const active = location.pathname === item.to
              || (item.to !== "/admin" && location.pathname.startsWith(`${item.to}/`));
            return (
              <Link key={item.to} to={item.to} className={`sidebar-link${active ? " sidebar-link-active" : ""}`}
                    aria-current={active ? "page" : undefined}>
                <span className="sidebar-icon" aria-hidden="true">{item.glyph}</span>
                {item.label}
              </Link>
            );
          })}
          {roleAtLeast(session.role, "ADMIN") && (
            <Link to="/dashboard" className="sidebar-link admin-console-exit">
              <span className="sidebar-icon" aria-hidden="true">⇤</span>
              Back to Mission Control
            </Link>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="sidebar-avatar" aria-hidden="true">{initials(session.displayName)}</span>
            <span className="sidebar-user-text">
              <span className="sidebar-user-name">{session.displayName}</span>
              <span className="sidebar-user-role">Administrator</span>
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
                  aria-label="Toggle navigation" aria-controls="admin-sidebar" aria-expanded={mobileOpen}>
            <span aria-hidden="true">☰</span>
          </button>
          <nav className="admin-breadcrumbs" aria-label="Breadcrumb">
            {trail.map((crumb, i) => (
              <span key={crumb.label}>
                {i > 0 && <span aria-hidden="true"> › </span>}
                {crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}
              </span>
            ))}
          </nav>
          <div className="topbar-right">
            <button type="button" className="topbar-button" onClick={() => setTheme(nextTheme[theme])}
                    aria-label="Toggle theme" title="Toggle theme">
              <span aria-hidden="true">{theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐"}</span>
            </button>
          </div>
        </header>

        <main id="main" className="shell-main">{children}</main>
      </div>
    </div>
  );
}
