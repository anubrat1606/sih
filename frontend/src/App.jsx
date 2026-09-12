import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth";
import { ToastProvider } from "./notifications";
import AppShell from "./shell/AppShell";
import BidderApp from "./bidder/BidderApp";

import LoginPage from "./pages/LoginPage";
import MissionControlPage from "./pages/MissionControlPage";
import TendersPage from "./pages/TendersPage";
import TenderDetailPage from "./pages/TenderDetailPage";
import BiddersPage from "./pages/BiddersPage";
import RegisterBidderPage from "./pages/RegisterBidderPage";
import BidderCompliancePage from "./pages/BidderCompliancePage";
import EvidenceGraphPage from "./pages/EvidenceGraphPage";
import DocumentsPage from "./pages/DocumentsPage";
import VerificationPage from "./pages/VerificationPage";
import CompliancePage from "./pages/CompliancePage";
import EvidencePage from "./pages/EvidencePage";
import ReportsPage from "./pages/ReportsPage";
import AuditTrailPage from "./pages/AuditTrailPage";
import SettingsPage from "./pages/SettingsPage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/officials/dashboard" replace />} />
      <Route path="/login" element={<LoginPage />} />

      <Route path="/dashboard" element={<RequireAuth><MissionControlPage /></RequireAuth>} />
      <Route path="/tenders" element={<RequireAuth><TendersPage /></RequireAuth>} />
      <Route path="/tenders/:tenderId" element={<RequireAuth><TenderDetailPage /></RequireAuth>} />

      {/* Static segment before the dynamic one, so /bidders/register is never
          read as a bidder whose id happens to be "register". */}
      <Route path="/bidders" element={<RequireAuth><BiddersPage /></RequireAuth>} />
      <Route path="/bidders/register" element={<RequireAuth><RegisterBidderPage /></RequireAuth>} />
      <Route path="/bidders/:bidderId" element={<RequireAuth><BidderCompliancePage /></RequireAuth>} />
      <Route path="/bidders/:bidderId/evidence-graph" element={<RequireAuth><EvidenceGraphPage /></RequireAuth>} />

      <Route path="/documents" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
      <Route path="/verification" element={<RequireAuth><VerificationPage /></RequireAuth>} />
      <Route path="/compliance" element={<RequireAuth><CompliancePage /></RequireAuth>} />
      <Route path="/evidence" element={<RequireAuth><EvidencePage /></RequireAuth>} />
      <Route path="/reports" element={<RequireAuth><ReportsPage /></RequireAuth>} />
      <Route path="/audit" element={<RequireAuth><AuditTrailPage /></RequireAuth>} />
      <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />

      <Route path="*" element={<Navigate to="/officials/dashboard" replace />} />
    </Routes>
  );
}

// The officer/admin application. Its own routes below are unchanged and
// still written as absolute paths ("/dashboard", "/tenders", ...) — that
// keeps matching correctly once mounted under "/officials/*" below, because
// a nested <Routes> matches against the pathname with the parent's matched
// prefix already stripped, so "/dashboard" here is compared against
// "/officials/dashboard" with "/officials" removed, i.e. "/dashboard".
// Only real browser-navigation targets (Link/navigate/Navigate, which are
// never prefix-stripped) needed the "/officials" prefix added.
function OfficerApp() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </AuthProvider>
    </ToastProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* The bidder portal is the public-facing application — it owns the
            root of the site, since bidders are this platform's general
            public and shouldn't need to know an internal path to find it. */}
        <Route path="/" element={<Navigate to="/bidder/dashboard" replace />} />
        <Route path="/bidder/*" element={<BidderApp />} />

        {/* The officer/admin application is deliberately moved off the
            public root to /officials — it's an internal tool, not the
            platform's front door, and its own login page lives there too. */}
        <Route path="/officials/*" element={<OfficerApp />} />

        <Route path="*" element={<Navigate to="/bidder/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
