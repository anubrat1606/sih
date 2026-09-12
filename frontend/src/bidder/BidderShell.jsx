import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useBidderSession } from "./BidderSessionContext";

// Mirrors the officer AppShell's structure (same sidebar/topbar layout
// classes from design/shell.css) but is a completely separate component
// tree with its own navigation, so nothing here can regress the officer
// portal and nothing there can leak into this one.
const NAV = [
  { to: "/bidder/dashboard", label: "Dashboard", glyph: "▦" },
  { to: "/bidder/tenders", label: "Tenders", glyph: "▤" },
  { to: "/bidder/my-bids", label: "My Bids", glyph: "☑" },
  { to: "/bidder/auctions", label: "Upcoming Auctions", glyph: "◔" },
  { to: "/bidder/results", label: "My Results", glyph: "✓" },
  { to: "/bidder/notifications", label: "Notifications", glyph: "◈" },
  { to: "/bidder/documents", label: "Documents", glyph: "▥" },
  { to: "/bidder/profile", label: "Profile", glyph: "◐" },
  { to: "/bidder/help", label: "Help", glyph: "?" },
];

function initials(name) {
  if (!name) return "B";
  return name.trim().slice(0, 2).toUpperCase();
}

export default function BidderShell({ children }) {
  const { profile, setProfile } = useBidderSession();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isAuthRoute = ["/bidder/signup", "/bidder/login", "/bidder/verify-email", "/bidder/verify-mobile"]
    .some((p) => location.pathname.startsWith(p));

  if (isAuthRoute) {
    // Auth pages get the minimal header, exactly like the officer portal's
    // signed-out shell -- there's no sidebar to navigate with before an
    // identity exists.
    return (
      <div className="signed-out">
        <header className="signed-out-header">
          <Link to="/bidder" className="sidebar-brand">
            <span className="sidebar-brand-mark">SATYAPRAMĀṆ</span>
            <span className="sidebar-brand-sub">Bidder Portal</span>
          </Link>
          <span className="signed-out-note">Every verdict traced to evidence, an authority and a rule version</span>
        </header>
        <main id="main">{children}</main>
      </div>
    );
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>

      <button type="button" className="shell-mobile-toggle" onClick={() => setMobileOpen((v) => !v)}
              aria-label="Toggle navigation" aria-controls="bidder-sidebar" aria-expanded={mobileOpen}>
        <span aria-hidden="true">☰</span>
      </button>

      <aside className={`sidebar${mobileOpen ? " sidebar-open" : ""}`} id="bidder-sidebar">
        <Link to="/bidder/dashboard" className="sidebar-brand">
          <span className="sidebar-brand-mark">SATYAPRAMĀṆ</span>
          <span className="sidebar-brand-sub">Bidder Portal</span>
        </Link>

        <nav className="sidebar-nav" aria-label="Main" onClick={() => setMobileOpen(false)}>
          {NAV.map((item) => {
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
            <span className="sidebar-avatar" aria-hidden="true">{initials(profile?.fullName)}</span>
            <span className="sidebar-user-text">
              <span className="sidebar-user-name">{profile?.fullName || "Guest bidder"}</span>
              <span className="sidebar-user-role">
                {profile ? (profile.emailVerified ? "Profile saved" : "Not verified") : "No profile yet"}
              </span>
            </span>
          </div>
          {profile ? (
            <button type="button" className="sidebar-action" onClick={() => setProfile(null)}>
              <span className="sidebar-icon" aria-hidden="true">⇥</span> Clear local profile
            </button>
          ) : (
            <Link to="/bidder/signup" className="sidebar-action">
              <span className="sidebar-icon" aria-hidden="true">＋</span> Create account
            </Link>
          )}
        </div>
      </aside>

      {mobileOpen && <div className="shell-scrim" onClick={() => setMobileOpen(false)} />}

      <div className="shell-body">
        <header className="topbar">
          <span className="page-eyebrow" style={{ margin: 0 }}>Bidder Portal</span>
          <span className="spacer" />
          <Link to="/bidder/notifications" className="topbar-button" aria-label="Notifications">
            <span aria-hidden="true">◈</span>
          </Link>
          <Link to="/bidder/profile" className="topbar-profile-trigger" style={{ textDecoration: "none" }}>
            <span className="topbar-avatar" aria-hidden="true">{initials(profile?.fullName)}</span>
            <span className="text-sm">{profile?.fullName || "Guest"}</span>
          </Link>
        </header>
        <main className="shell-main" id="main">{children}</main>
      </div>
    </div>
  );
}
