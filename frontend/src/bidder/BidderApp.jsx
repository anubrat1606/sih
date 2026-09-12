import { Navigate, Route, Routes } from "react-router-dom";
import { BidderSessionProvider } from "./BidderSessionContext";
import BidderShell from "./BidderShell";

import SignUpPage from "./pages/SignUpPage";
import LoginPage from "./pages/LoginPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import VerifyMobilePage from "./pages/VerifyMobilePage";
import DashboardPage from "./pages/DashboardPage";
import TendersPage from "./pages/TendersPage";
import TenderDetailPage from "./pages/TenderDetailPage";
import ParticipatePage from "./pages/ParticipatePage";
import AuctionPage from "./pages/AuctionPage";
import MyBidsPage from "./pages/MyBidsPage";
import ResultsPage from "./pages/ResultsPage";
import NotificationsPage from "./pages/NotificationsPage";
import DocumentsPage from "./pages/DocumentsPage";
import ProfilePage from "./pages/ProfilePage";
import HelpPage from "./pages/HelpPage";

// Entirely separate from the officer application's routes/providers/shell.
// There is no BIDDER role in the backend and therefore no real
// authentication gate here (see BidderSessionContext.jsx) — every route
// below is reachable by anyone, exactly like the underlying open endpoints
// it reads from.
function BidderRoutes() {
  return (
    <Routes>
      <Route path="/bidder" element={<Navigate to="/bidder/dashboard" replace />} />

      <Route path="/bidder/signup" element={<SignUpPage />} />
      <Route path="/bidder/login" element={<LoginPage />} />
      <Route path="/bidder/verify-email" element={<VerifyEmailPage />} />
      <Route path="/bidder/verify-mobile" element={<VerifyMobilePage />} />

      <Route path="/bidder/dashboard" element={<DashboardPage />} />
      <Route path="/bidder/tenders" element={<TendersPage />} />
      <Route path="/bidder/tenders/:tenderId" element={<TenderDetailPage />} />
      <Route path="/bidder/tenders/:tenderId/participate" element={<ParticipatePage />} />
      <Route path="/bidder/auctions" element={<AuctionPage />} />
      <Route path="/bidder/tenders/:tenderId/auction" element={<AuctionPage />} />
      <Route path="/bidder/my-bids" element={<MyBidsPage />} />
      <Route path="/bidder/results" element={<ResultsPage />} />
      <Route path="/bidder/notifications" element={<NotificationsPage />} />
      <Route path="/bidder/documents" element={<DocumentsPage />} />
      <Route path="/bidder/profile" element={<ProfilePage />} />
      <Route path="/bidder/help" element={<HelpPage />} />

      <Route path="/bidder/*" element={<Navigate to="/bidder/dashboard" replace />} />
    </Routes>
  );
}

export default function BidderApp() {
  return (
    <BidderSessionProvider>
      <BidderShell>
        <BidderRoutes />
      </BidderShell>
    </BidderSessionProvider>
  );
}
