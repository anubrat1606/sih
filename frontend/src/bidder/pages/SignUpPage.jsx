import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signUp } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import {
  formatIndianMobile, isPasswordValid, isValidEmail, isValidIndianMobile,
  normalizeIndianMobile, PasswordStrengthMeter,
} from "../components/FormControls";
import { ErrorState } from "../../ui/primitives";

const initial = {
  fullName: "", email: "", mobile: "", password: "", confirmPassword: "",
  companyName: "", gstin: "", acceptedTerms: false,
};

export default function SignUpPage() {
  const navigate = useNavigate();
  const { setSession } = useBidderSession();
  const [form, setForm] = useState(initial);
  const [touched, setTouched] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const touch = (key) => () => setTouched((t) => ({ ...t, [key]: true }));

  const emailValid = form.email === "" ? null : isValidEmail(form.email);
  const mobileValid = form.mobile === "" ? null : isValidIndianMobile(form.mobile);
  const passwordValid = isPasswordValid(form.password);
  const confirmValid = form.confirmPassword === "" ? null : form.confirmPassword === form.password;

  const canSubmit = form.fullName.trim() && emailValid && mobileValid && passwordValid
    && confirmValid && form.companyName.trim() && form.acceptedTerms;

  async function onSubmit(e) {
    e.preventDefault();
    setTouched({ fullName: true, email: true, mobile: true, password: true, confirmPassword: true, companyName: true, acceptedTerms: true });
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const { token, bidder } = await signUp({
        fullName: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
        mobile: normalizeIndianMobile(form.mobile),
        companyName: form.companyName.trim(),
        gstin: form.gstin.trim() || null,
      });
      setSession({ token, bidder });
      navigate("/bidder/verify-email");
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card auth-card-wide">
        <div className="card-body">
          <div className="page-eyebrow">Bidder account</div>
          <h1 className="section-title" style={{ marginBottom: 4 }}>Create your account</h1>
          <p className="text-sm text-secondary" style={{ marginBottom: 20 }}>
            Register once to discover tenders, track your submissions and view your results.
          </p>

          <ErrorState error={error} />

          <form className="form form-wide" onSubmit={onSubmit} noValidate>
            <div className="form-row">
              <div className="field">
                <label htmlFor="su-name">Full name</label>
                <input id="su-name" value={form.fullName} onChange={set("fullName")} onBlur={touch("fullName")} required />
                {touched.fullName && !form.fullName.trim() && <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Full name is required.</span>}
              </div>
              <div className="field">
                <label htmlFor="su-company">Company / organization name</label>
                <input id="su-company" value={form.companyName} onChange={set("companyName")} onBlur={touch("companyName")} required />
                {touched.companyName && !form.companyName.trim() && <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Organization name is required.</span>}
              </div>
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="su-email">Email address</label>
                <input id="su-email" type="email" value={form.email} onChange={set("email")} onBlur={touch("email")} required
                       aria-invalid={touched.email && emailValid === false} />
                {touched.email && emailValid === false && (
                  <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Enter a valid email address.</span>
                )}
              </div>
              <div className="field">
                <label htmlFor="su-mobile">Mobile number <span className="field-hint">Indian +91 number</span></label>
                <input id="su-mobile" className="mono" value={form.mobile} onChange={set("mobile")} onBlur={touch("mobile")}
                       placeholder="+91 98765 43210" required aria-invalid={touched.mobile && mobileValid === false} />
                {touched.mobile && mobileValid === false && (
                  <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Enter a valid 10-digit Indian mobile number.</span>
                )}
                {mobileValid && (
                  <span className="field-hint">Will be stored as <span className="mono">{formatIndianMobile(normalizeIndianMobile(form.mobile))}</span></span>
                )}
              </div>
            </div>

            <div className="field">
              <label htmlFor="su-gstin">GSTIN <span className="field-hint">optional — can be added later</span></label>
              <input id="su-gstin" className="mono" value={form.gstin} onChange={set("gstin")} placeholder="27AAAAA0000A1Z5" />
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="su-pass">Password</label>
                <input id="su-pass" type="password" autoComplete="new-password" value={form.password}
                       onChange={set("password")} onBlur={touch("password")} required />
                <PasswordStrengthMeter password={form.password} />
              </div>
              <div className="field">
                <label htmlFor="su-confirm">Confirm password</label>
                <input id="su-confirm" type="password" autoComplete="new-password" value={form.confirmPassword}
                       onChange={set("confirmPassword")} onBlur={touch("confirmPassword")} required
                       aria-invalid={touched.confirmPassword && confirmValid === false} />
                {touched.confirmPassword && confirmValid === false && (
                  <span className="field-hint" style={{ color: "var(--status-fail-fg)" }}>Passwords do not match.</span>
                )}
              </div>
            </div>

            <label className="checkbox-field">
              <input type="checkbox" checked={form.acceptedTerms}
                     onChange={(e) => setForm((f) => ({ ...f, acceptedTerms: e.target.checked }))} />
              <span>I accept the Terms &amp; Conditions and the data-handling notice for this platform.</span>
            </label>

            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p className="text-sm text-secondary" style={{ marginTop: 20 }}>
            Already have an account? <Link to="/bidder/login">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
