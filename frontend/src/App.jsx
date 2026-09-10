import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import DashboardPage from "./pages/DashboardPage";
import BidderDetailPage from "./pages/BidderDetailPage";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="topnav">
        <Link to="/upload">Upload</Link>
        <span className="topnav-note">SIH26100 — GeM Bid Compliance (real data only)</span>
      </nav>
      <Routes>
        <Route path="/" element={<Navigate to="/upload" replace />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/dashboard/:tenderId" element={<DashboardPage />} />
        <Route path="/bidder/:bidderId" element={<BidderDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
}
