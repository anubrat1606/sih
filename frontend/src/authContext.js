// Split out of auth.jsx so that file can stay component-only (Fast Refresh
// only works when a file exports nothing but components -- the same reason
// theme.js exists separately from components.jsx).
import { createContext, useContext } from "react";

export const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside an AuthProvider");
  return ctx;
}

const ROLE_ORDER = { OFFICER: 0, SENIOR_OFFICER: 1, ADMIN: 2 };

export function roleAtLeast(role, minimum) {
  return (ROLE_ORDER[role] ?? -1) >= ROLE_ORDER[minimum];
}
