import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth, RequireRole } from "./auth";
import { useAuth } from "./authContext";
import { ToastProvider } from "./notifications";
import AppShell from "./shell/AppShell";
import BidderShell from "./bidder/shell/BidderShell";
import "./bidder/bidder.css";

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

// A bidder's whole tree, mounted at /portal/*. Empty-but-real for now (A2)
// -- Rishika, Suhani, and Kevin's pages (round 6) get added here as their
// own PRs land; nothing here fabricates a page that isn't built yet.
function PortalRoutes() {
  return (
    <RequireRole role="BIDDER">
      <BidderShell>
        <Routes>
          <Route index element={
            <div className="page">
              <h1>Bidder Dashboard</h1>
              <p className="hint">This round's pages are landing one PR at a time — check back shortly.</p>
            </div>
          } />
        </Routes>
      </BidderShell>
    </RequireRole>
  );
}

// Signed-in bidders land on /portal, everyone else on /dashboard -- a
// plain unconditional redirect here would send a bidder into an officer
// page that now correctly 403s server-side instead of the portal they
// actually have.
function RootRedirect() {
  const { session, checking } = useAuth();
  // Wait for a stored session to be confirmed against the real backend
  // before deciding where to send it -- otherwise a bidder refreshing on
  // "/" would be redirected to /dashboard during the brief window before
  // their session is restored, and land in the wrong shell.
  if (checking) return <div className="page"><p className="hint">Checking session…</p></div>;
  return <Navigate to={session?.role === "BIDDER" ? "/portal" : "/dashboard"} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/portal/*" element={<PortalRoutes />} />
            <Route path="/*" element={<OfficerRoutes />} />
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
