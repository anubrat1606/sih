import { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../authContext";
import { ErrorBox } from "../components";

export default function LoginPage() {
  const { session, login } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Already signed in -- land back wherever RequireAuth sent them from, or
  // the tenders list by default. Declarative redirect, not a navigate()
  // call during render.
  if (session) {
    return <Navigate to={location.state?.from?.pathname || "/tenders"} replace />;
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      // The redirect above handles getting them where they were headed --
      // this render will re-run with session set and take that branch.
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page page-narrow">
      <h1>Sign in</h1>
      <p className="hint">
        SATYAPRAMĀṆA — officer access only. There is no self-signup; an administrator
        creates every account.
      </p>
      <ErrorBox error={error} />
      <form className="form" onSubmit={onSubmit}>
        <label>Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </label>
        <label>Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <button type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
