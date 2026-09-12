import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { setBidderToken } from "./bidderApi";

// A real, authenticated bidder session now that satyapramana_store/
// bidder_auth/ exists on the backend -- {token, bidder}, exactly the shape
// signUp()/login()/continueWithGoogle() in bidderApi.js resolve to. Held
// here in React state and mirrored into bidderApi.js's module-level
// bidderToken (via setBidderToken) so every subsequent request carries it,
// the same two-places-in-sync pattern auth.jsx/api.js already use for
// officers.
//
// `tracked` stays a separate, purely local list of bidder_id/tender_id
// pairs this browser has registered on -- that isn't part of the account
// (a bidder acting from a second device wouldn't see it), it's a
// convenience so "My Bids" has something to show without a
// GET /bidders?email=... endpoint, which doesn't exist and would leak
// every bidder's records to any authenticated bidder if it did.

const STORAGE_KEY = "satyapramana-bidder-session";
const TRACKED_KEY = "satyapramana-bidder-tracked-bids";

const BidderSessionContext = createContext(null);

function loadSession() {
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
  const [session, setSessionState] = useState(loadSession);
  const [tracked, setTrackedState] = useState(loadTracked);

  // Restore the token into bidderApi.js on first mount (and whenever the
  // session changes) -- a page refresh must not silently drop back to an
  // unauthenticated bidderApi module while React state still thinks
  // there's a session.
  useEffect(() => {
    setBidderToken(session?.token || null);
  }, [session]);

  const setSession = useCallback((next) => {
    setSessionState(next);
    try {
      if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else localStorage.removeItem(STORAGE_KEY);
    } catch { /* private browsing / storage blocked */ }
  }, []);

  // Merges a fresh bidder profile (e.g. after verifying email/mobile) into
  // the current session without requiring a full re-login.
  const updateBidder = useCallback((patch) => {
    setSessionState((cur) => {
      if (!cur) return cur;
      const next = { ...cur, bidder: { ...cur.bidder, ...patch } };
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* blocked */ }
      return next;
    });
  }, []);

  const clearSession = useCallback(() => setSession(null), [setSession]);

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

  return (
    <BidderSessionContext.Provider value={{
      session, bidder: session?.bidder || null, isAuthenticated: Boolean(session),
      setSession, updateBidder, clearSession, tracked, trackBid, forgetBid,
    }}>
      {children}
    </BidderSessionContext.Provider>
  );
}

export function useBidderSession() {
  const ctx = useContext(BidderSessionContext);
  if (!ctx) throw new Error("useBidderSession() must be used inside a BidderSessionProvider");
  return ctx;
}
