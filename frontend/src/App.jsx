import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth";
import { useAuth } from "./authContext";
import StatusPage from "./pages/StatusPage";
import LoginPage from "./pages/LoginPage";
import TendersPage from "./pages/TendersPage";
import RegisterBidderPage from "./pages/RegisterBidderPage";
import TenderDashboardPage from "./pages/TenderDashboardPage";
import BidderDetailPage from "./pages/BidderDetailPage";
import EvidenceGraphPage from "./pages/EvidenceGraphPage";
import AuditPage from "./pages/AuditPage";
import "./App.css";

// Light is the default; dark is not a filter over it -- both are first-class
// (satyapramana.md 2.3). "system" defers to prefers-color-scheme entirely
// (no data-theme attribute at all); an explicit choice sets data-theme and
// persists it, so a returning officer's choice sticks across sessions.
function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("satyapramana-theme") || "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("satyapramana-theme", theme);
    } catch {
      // Private browsing / storage blocked -- the toggle still works for
      // this page view, it just won't persist. Not worth failing over.
    }
  }, [theme]);

  return [theme, setTheme];
}

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = { system: "light", light: "dark", dark: "system" };
  const label = { system: "Theme: system", light: "Theme: light", dark: "Theme: dark" };
  return (
    <button className="theme-toggle" onClick={() => setTheme(next[theme])}>
      {label[theme]}
    </button>
  );
}

// Identity + sign-out, shown in the topnav once a session exists. Signed
// out, this renders nothing here -- LoginPage is where signing in happens,
// not the nav bar.
function AccountBadge() {
  const { session, logout } = useAuth();
  if (!session) return null;
  return (
    <span className="account-badge">
      <span className="mono">{session.displayName}</span>
      <span className="account-role">{session.role.replace("_", " ")}</span>
      <button type="button" className="account-logout" onClick={logout}>Sign out</button>
    </span>
  );
}

function Nav() {
  const { session } = useAuth();
  return (
    <nav className="topnav">
      <Link to="/">Status</Link>
      {session && (
        <>
          <Link to="/tenders">Tenders</Link>
          <Link to="/register">Register bidder</Link>
          <Link to="/audit">Audit log</Link>
        </>
      )}
      <span className="topnav-note">SATYAPRAMĀṆA — real data only, no simulated authority response</span>
      <AccountBadge />
      <ThemeToggle />
    </nav>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<StatusPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/tenders" element={<RequireAuth><TendersPage /></RequireAuth>} />
      <Route path="/register" element={<RequireAuth><RegisterBidderPage /></RequireAuth>} />
      <Route path="/tenders/:tenderId" element={<RequireAuth><TenderDashboardPage /></RequireAuth>} />
      <Route path="/bidders/:bidderId" element={<RequireAuth><BidderDetailPage /></RequireAuth>} />
      <Route path="/bidders/:bidderId/evidence-graph" element={<RequireAuth><EvidenceGraphPage /></RequireAuth>} />
      <Route path="/audit" element={<RequireAuth><AuditPage /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Nav />
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
