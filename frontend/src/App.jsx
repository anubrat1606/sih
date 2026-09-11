import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import StatusPage from "./pages/StatusPage";
import TendersPage from "./pages/TendersPage";
import RegisterBidderPage from "./pages/RegisterBidderPage";
import TenderDashboardPage from "./pages/TenderDashboardPage";
import BidderDetailPage from "./pages/BidderDetailPage";
import AuditPage from "./pages/AuditPage";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="topnav">
        <Link to="/">Status</Link>
        <Link to="/tenders">Tenders</Link>
        <Link to="/register">Register bidder</Link>
        <Link to="/audit">Audit log</Link>
        <span className="topnav-note">SATYAPRAMĀṆA — real data only, no simulated authority response</span>
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
