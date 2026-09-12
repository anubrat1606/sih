import { createContext, useCallback, useContext, useEffect, useState } from "react";

// There is no bidder identity backend yet (see bidderApi.js), so there is
// no real session to hold here. What this context actually holds is a
// browser-local *profile draft* -- the name/email/mobile a visitor typed
// into Sign Up, and which bidder_id/tender_id pairs they've registered or
// looked up in this browser -- so the portal is usable and demonstrable
// today without pretending any of it is an authenticated account.
//
// This is never presented as "signed in." Every page that reads it says so
// plainly. The moment a real backend identity system exists, this whole
// file is replaced by a real session (JWT + /auth/me, the same pattern
// AuthProvider already uses for officers) -- nothing downstream should
// need to change its own logic, only where the session comes from.

const STORAGE_KEY = "satyapramana-bidder-profile-draft";
const TRACKED_KEY = "satyapramana-bidder-tracked-bids";

const BidderSessionContext = createContext(null);

function loadDraft() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function loadTracked() {
  try {
    const raw = localStorage.getItem(TRACKED_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function BidderSessionProvider({ children }) {
  const [profile, setProfileState] = useState(loadDraft);
  const [tracked, setTrackedState] = useState(loadTracked);

  const setProfile = useCallback((next) => {
    setProfileState(next);
    try {
      if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else localStorage.removeItem(STORAGE_KEY);
    } catch { /* private browsing / storage blocked */ }
  }, []);

  // Remember a bidder_id/tender_id pair this browser has actually
  // participated in or looked up for real, so "My Bids" has something
  // genuine to show without a real account system -- never a fabricated
  // entry, only ones a real registerBidder() call actually produced.
  const trackBid = useCallback((tenderId, bidderId) => {
    setTrackedState((cur) => {
      const next = [
        { tenderId, bidderId, trackedAt: new Date().toISOString() },
        ...cur.filter((t) => !(t.tenderId === tenderId && t.bidderId === bidderId)),
      ];
      try { localStorage.setItem(TRACKED_KEY, JSON.stringify(next)); } catch { /* blocked */ }
      return next;
    });
  }, []);

  const forgetBid = useCallback((tenderId, bidderId) => {
    setTrackedState((cur) => {
      const next = cur.filter((t) => !(t.tenderId === tenderId && t.bidderId === bidderId));
      try { localStorage.setItem(TRACKED_KEY, JSON.stringify(next)); } catch { /* blocked */ }
      return next;
    });
  }, []);

  useEffect(() => {
    setTrackedState(loadTracked());
  }, []);

  return (
    <BidderSessionContext.Provider value={{ profile, setProfile, tracked, trackBid, forgetBid }}>
      {children}
    </BidderSessionContext.Provider>
  );
}

export function useBidderSession() {
  const ctx = useContext(BidderSessionContext);
  if (!ctx) throw new Error("useBidderSession() must be used inside a BidderSessionProvider");
  return ctx;
}
