import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth, RequireRole } from "./auth";
import { useAuth } from "./authContext";
import { ToastProvider } from "./notifications";
import AppShell from "./shell/AppShell";
import BidderShell from "./bidder/shell/BidderShell";
import "./bidder/bidder.css";

import BidderDashboardPage from "./bidder/pages/DashboardPage";
import BidderTendersPage from "./bidder/pages/TendersPage";
import BidderTenderDetailPage from "./bidder/pages/TenderDetailPage";
import SubmissionsPage from "./bidder/pages/SubmissionsPage";
import SubmitDocumentsPage from "./bidder/pages/SubmitDocumentsPage";
import ResultsPage from "./bidder/pages/ResultsPage";
import NotificationsPage from "./bidder/pages/NotificationsPage";
import ProfilePage from "./bidder/pages/ProfilePage";
import HelpPage from "./bidder/pages/HelpPage";

import LandingPage from "./landing/LandingPage";
import LoginPage from "./pages/LoginPage";
import MissionControlPage from "./pages/MissionControlPage";
import TendersPage from "./pages/TendersPage";
import TenderDetailPage from "./pages/TenderDetailPage";
import BiddersPage from "./pages/BiddersPage";
import RegisterBidderPage from "./pages/RegisterBidderPage";
import BidderCompliancePage from "./pages/BidderCompliancePage";
import ReviewQueuePage from "./officer/review/ReviewQueuePage";
import EvidenceGraphPage from "./pages/EvidenceGraphPage";
import DocumentsPage from "./pages/DocumentsPage";
import VerificationPage from "./pages/VerificationPage";
import CompliancePage from "./pages/CompliancePage";
import EvidencePage from "./pages/EvidencePage";
import ReportsPage from "./pages/ReportsPage";
import AuditTrailPage from "./pages/AuditTrailPage";
import SettingsPage from "./pages/SettingsPage";

// Not role-aware inside here on purpose: every officer route already
// requires a real server-side officer role for anything it actually reads
// or writes (see the A1 retrofit, docs/PERFORMANCE_AUDIT.md-adjacent
// security fix) -- RequireAuth's job is only "is anyone signed in", the
// same as before this round. This whole tree is completely untouched
// except for being moved inside its own component so a bidder session can
// get a different top-level branch instead.
function OfficerRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route path="/dashboard" element={<RequireAuth><MissionControlPage /></RequireAuth>} />
        <Route path="/tenders" element={<RequireAuth><TendersPage /></RequireAuth>} />
        <Route path="/tenders/:tenderId" element={<RequireAuth><TenderDetailPage /></RequireAuth>} />

        {/* Static segment before the dynamic one, so /bidders/register is
            never read as a bidder whose id happens to be "register". */}
        <Route path="/bidders" element={<RequireAuth><BiddersPage /></RequireAuth>} />
        <Route path="/review" element={<RequireAuth><ReviewQueuePage /></RequireAuth>} />
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

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}

// A bidder's whole tree, mounted at /portal/*. Round 6, A6: every page
// Rishika (R1-R4), Suhani (S1-S3), and Kevin (K1-K3) built in their own
// isolated files, wired together here in the one integration commit --
// the same pattern used all through this project's earlier rounds.
function PortalRoutes() {
  return (
    <RequireRole role="BIDDER">
      <BidderShell>
        <Routes>
          <Route index element={<BidderDashboardPage />} />
          <Route path="tenders" element={<BidderTendersPage />} />
          <Route path="tenders/:tenderId" element={<BidderTenderDetailPage />} />
          <Route path="tenders/:tenderId/submit" element={<SubmitDocumentsPage />} />
          <Route path="submissions" element={<SubmissionsPage />} />
          <Route path="results" element={<ResultsPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="help" element={<HelpPage />} />
          <Route path="*" element={<Navigate to="/portal" replace />} />
        </Routes>
      </BidderShell>
    </RequireRole>
  );
}

// "/" is the public landing page for anyone signed out. A live session
// skips it: bidders go to /portal, everyone else to /dashboard -- a plain
// unconditional redirect would send a bidder into an officer page that
// correctly 403s server-side instead of the portal they actually have.
function RootGate() {
  const { session, checking } = useAuth();
  // Wait for a stored session to be confirmed against the real backend
  // before deciding -- otherwise a bidder refreshing on "/" would flash the
  // landing page (or be sent to /dashboard) during the brief window before
  // their session is restored.
  if (checking) return <div className="page"><p className="hint">Checking session…</p></div>;
  if (session) return <Navigate to={session.role === "BIDDER" ? "/portal" : "/dashboard"} replace />;
  return <LandingPage />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<RootGate />} />
            <Route path="/portal/*" element={<PortalRoutes />} />
            <Route path="/*" element={<OfficerRoutes />} />
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
