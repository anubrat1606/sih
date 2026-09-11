import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth";
import { ToastProvider } from "./notifications";
import AppShell from "./AppShell";
import StatusPage from "./pages/StatusPage";
import LoginPage from "./pages/LoginPage";
import TendersPage from "./pages/TendersPage";
import RegisterBidderPage from "./pages/RegisterBidderPage";
import TenderDashboardPage from "./pages/TenderDashboardPage";
import BidderDetailPage from "./pages/BidderDetailPage";
import EvidenceGraphPage from "./pages/EvidenceGraphPage";
import AuditPage from "./pages/AuditPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import DashboardPage from "./pages/DashboardPage";
import "./App.css";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<StatusPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/tenders" element={<RequireAuth><TendersPage /></RequireAuth>} />
      <Route path="/register" element={<RequireAuth><RegisterBidderPage /></RequireAuth>} />
      <Route path="/tenders/:tenderId" element={<RequireAuth><TenderDashboardPage /></RequireAuth>} />
      <Route path="/bidders/:bidderId" element={<RequireAuth><BidderDetailPage /></RequireAuth>} />
      <Route path="/bidders/:bidderId/evidence-graph" element={<RequireAuth><EvidenceGraphPage /></RequireAuth>} />
      <Route path="/audit" element={<RequireAuth><AuditPage /></RequireAuth>} />
      <Route path="/admin/users" element={<RequireAuth><AdminUsersPage /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
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
