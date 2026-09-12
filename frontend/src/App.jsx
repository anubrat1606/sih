import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth";
import { ToastProvider } from "./notifications";
import AppShell from "./shell/AppShell";

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
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
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

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <AppShell>
            <AppRoutes />
          </AppShell>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
