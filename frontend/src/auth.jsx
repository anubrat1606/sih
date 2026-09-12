// Session state for the whole app -- one AuthProvider wraps <App>, and any
// component reads it with useAuth() (authContext.js). The token itself
// lives in localStorage (survives a refresh) and is mirrored into api.js's
// module-level authToken via setAuthToken() so every fetch call() makes
// picks it up automatically -- no component ever attaches an Authorization
// header itself.
import { useCallback, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getMe, login as apiLogin, setAuthToken } from "./api";
import { AuthContext, useAuth } from "./authContext";

const STORAGE_KEY = "satyapramana-session";

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null; // private browsing / storage blocked -- just start signed out
  }
}

function saveStored(session) {
  try {
    if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Session still works for this tab; it just won't survive a refresh.
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  // Starts true: a stored session (if any) is checked against the real
  // backend before render settles, so a page never flashes "signed out"
  // for a token that's actually still valid.
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    (async () => {
      const stored = loadStored();
      if (!stored) {
        setChecking(false);
        return;
      }
      setAuthToken(stored.token);
      try {
        await getMe(); // confirms the token hasn't expired or been revoked
        setSession(stored);
      } catch {
        setAuthToken(null);
        saveStored(null);
        setSession(null);
      } finally {
        setChecking(false);
      }
    })();
  }, []);

  const login = useCallback(async (username, password) => {
    const body = await apiLogin(username, password);
    const next = {
      token: body.token, username: body.username,
      displayName: body.display_name, role: body.role,
    };
    setAuthToken(next.token);
    saveStored(next);
    setSession(next);
    return next;
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    saveStored(null);
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider value={{ session, checking, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// Wrap any route element that needs a signed-in officer. Redirects to
// /login and remembers where the visitor was headed, so a successful login
// returns them there instead of dumping them on the tenders list.
export function RequireAuth({ children }) {
  const { session, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="page"><p className="hint">Checking session…</p></div>;
  if (!session) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

// Wrap a route tree that belongs to exactly one side of the app. Unlike
// RequireAuth, this checks the LITERAL role, not a minimum -- an officer
// hitting a bidder route is a wrong-portal mistake, not a permission gap,
// so they're sent to their own home rather than refused outright, and the
// same the other way round. Signed-out visitors still go to /login first.
export function RequireRole({ role, children }) {
  const { session, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="page"><p className="hint">Checking session…</p></div>;
  if (!session) return <Navigate to="/login" state={{ from: location }} replace />;
  if (session.role !== role) {
    return <Navigate to={session.role === "BIDDER" ? "/portal" : "/dashboard"} replace />;
  }
  return children;
}
