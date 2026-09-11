import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import StatusPage from "./pages/StatusPage";
import TendersPage from "./pages/TendersPage";
import RegisterBidderPage from "./pages/RegisterBidderPage";
import TenderDashboardPage from "./pages/TenderDashboardPage";
import BidderDetailPage from "./pages/BidderDetailPage";
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

export default function App() {
  return (
    <BrowserRouter>
      <nav className="topnav">
        <Link to="/">Status</Link>
        <Link to="/tenders">Tenders</Link>
        <Link to="/register">Register bidder</Link>
        <Link to="/audit">Audit log</Link>
        <span className="topnav-note">SATYAPRAMĀṆA — real data only, no simulated authority response</span>
        <ThemeToggle />
      </nav>
      <Routes>
        <Route path="/" element={<StatusPage />} />
        <Route path="/tenders" element={<TendersPage />} />
        <Route path="/register" element={<RegisterBidderPage />} />
        <Route path="/tenders/:tenderId" element={<TenderDashboardPage />} />
        <Route path="/bidders/:bidderId" element={<BidderDetailPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
