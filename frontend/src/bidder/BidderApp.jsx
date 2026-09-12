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
  // This tree is mounted at <Route path="/bidder/*"> in App.jsx. A nested
  // <Routes> like this one matches against the pathname with that parent
  // prefix already stripped — so these paths must be relative ("dashboard",
  // not "/bidder/dashboard"). Using the absolute form here previously meant
  // none of these routes ever matched anything, leaving the shell's header
  // rendered with a permanently blank body below it.
  return (
    <Routes>
      <Route index element={<Navigate to="dashboard" replace />} />

      <Route path="signup" element={<SignUpPage />} />
      <Route path="login" element={<LoginPage />} />
      <Route path="verify-email" element={<VerifyEmailPage />} />
      <Route path="verify-mobile" element={<VerifyMobilePage />} />

      <Route path="dashboard" element={<DashboardPage />} />
      <Route path="tenders" element={<TendersPage />} />
      <Route path="tenders/:tenderId" element={<TenderDetailPage />} />
      <Route path="tenders/:tenderId/participate" element={<ParticipatePage />} />
      <Route path="auctions" element={<AuctionPage />} />
      <Route path="tenders/:tenderId/auction" element={<AuctionPage />} />
      <Route path="my-bids" element={<MyBidsPage />} />
      <Route path="results" element={<ResultsPage />} />
      <Route path="notifications" element={<NotificationsPage />} />
      <Route path="documents" element={<DocumentsPage />} />
      <Route path="profile" element={<ProfilePage />} />
      <Route path="help" element={<HelpPage />} />

      <Route path="*" element={<Navigate to="dashboard" replace />} />
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
