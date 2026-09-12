import { useEffect, useRef, useState } from "react";

/* ------------------------------------------------------------- email/mobile */

export function isValidEmail(value) {
  // Standard, pragmatic RFC-5322-ish check -- rejects the obviously
  // malformed (no @, no domain, spaces) without trying to be a full grammar.
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim());
}

// Indian mobile numbers: 10 digits, first digit 6-9, optionally prefixed
// with +91 / 91 / 0. Applied after stripping spaces and dashes, so
// "+91 98765 43210" or "98765-43210" (both ordinary ways to type a phone
// number) normalize the same as "9876543210" -- matches the backend's
// bidder_auth/validation.py exactly, so a number this form accepts is never
// one the server then rejects. Normalizes to a bare 10-digit string for
// storage and to "+91 XXXXX XXXXX" for display.
const MOBILE_RE = /^(?:\+?91|0)?([6-9]\d{9})$/;

export function isValidIndianMobile(value) {
  return normalizeIndianMobile(value) !== null;
}

export function normalizeIndianMobile(value) {
  const cleaned = value.trim().replace(/[\s-]/g, "");
  const m = cleaned.match(MOBILE_RE);
  return m ? m[1] : null;
}

export function formatIndianMobile(tenDigits) {
  if (!tenDigits || tenDigits.length !== 10) return tenDigits || "";
  return `+91 ${tenDigits.slice(0, 5)} ${tenDigits.slice(5)}`;
}

/* --------------------------------------------------------------- password */

export function passwordRules(pw) {
  return {
    length: pw.length >= 8,
    upper: /[A-Z]/.test(pw),
    lower: /[a-z]/.test(pw),
    digit: /[0-9]/.test(pw),
    special: /[^A-Za-z0-9]/.test(pw),
  };
}

export function passwordScore(pw) {
  const rules = passwordRules(pw);
  return Object.values(rules).filter(Boolean).length; // 0-5
}

export function isPasswordValid(pw) {
  return passwordScore(pw) === 5;
}

const STRENGTH_LABEL = ["Too weak", "Weak", "Fair", "Good", "Strong", "Strong"];
const STRENGTH_CLASS = ["fail", "fail", "partial", "partial", "pass", "pass"];

export function PasswordStrengthMeter({ password }) {
  const score = passwordScore(password);
  const rules = passwordRules(password);
  return (
    <div className="password-meter">
      <div className="password-meter-track">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={`password-meter-seg${i < score ? ` password-meter-seg-${STRENGTH_CLASS[score]}` : ""}`} />
        ))}
      </div>
      <div className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
        <span className={`text-xs ${score > 0 ? "" : "text-muted"}`}
              style={score > 0 ? { color: `var(--status-${STRENGTH_CLASS[score]}-fg)`, fontWeight: 600 } : undefined}>
          {password ? STRENGTH_LABEL[score] : "Enter a password"}
        </span>
      </div>
      <ul className="password-rules">
        <li className={rules.length ? "password-rule-met" : ""}>{rules.length ? "✓" : "○"} At least 8 characters</li>
        <li className={rules.upper ? "password-rule-met" : ""}>{rules.upper ? "✓" : "○"} One uppercase letter</li>
        <li className={rules.lower ? "password-rule-met" : ""}>{rules.lower ? "✓" : "○"} One lowercase letter</li>
        <li className={rules.digit ? "password-rule-met" : ""}>{rules.digit ? "✓" : "○"} One number</li>
        <li className={rules.special ? "password-rule-met" : ""}>{rules.special ? "✓" : "○"} One special character</li>
      </ul>
    </div>
  );
}

/* --------------------------------------------------------------------- OTP */

export function OtpInput({ length = 6, value, onChange, disabled }) {
  const refs = useRef([]);
  const digits = value.split("").concat(Array(length).fill("")).slice(0, length);

  function setDigit(i, d) {
    const next = digits.slice();
    next[i] = d;
    onChange(next.join(""));
    if (d && i < length - 1) refs.current[i + 1]?.focus();
  }

  function onKeyDown(i, e) {
    if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
  }

  function onPaste(e) {
    const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
    if (!text) return;
    e.preventDefault();
    onChange(text.padEnd(length, ""));
    refs.current[Math.min(text.length, length - 1)]?.focus();
  }

  return (
    <div className="otp-input" role="group" aria-label={`${length}-digit verification code`}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          className="otp-digit mono"
          inputMode="numeric"
          maxLength={1}
          value={d}
          disabled={disabled}
          onChange={(e) => setDigit(i, e.target.value.replace(/\D/g, "").slice(-1))}
          onKeyDown={(e) => onKeyDown(i, e)}
          onPaste={onPaste}
          aria-label={`Digit ${i + 1} of ${length}`}
        />
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- countdown */

export function useCountdown(seconds) {
  const [remaining, setRemaining] = useState(seconds);
  useEffect(() => {
    setRemaining(seconds);
  }, [seconds]);
  useEffect(() => {
    if (remaining <= 0) return;
    const id = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(id);
  }, [remaining > 0]); // eslint-disable-line react-hooks/exhaustive-deps
  return remaining;
}

export function formatCountdown(totalSeconds) {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
  return `${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}

/* --------------------------------------------------------------- stepper */

export function Stepper({ steps, current }) {
  return (
    <ol className="bidder-stepper" aria-label="Progress">
      {steps.map((label, i) => {
        const state = i < current ? "done" : i === current ? "active" : "pending";
        return (
          <li key={label} className={`bidder-step bidder-step-${state}`}>
            <span className="bidder-step-dot" aria-hidden="true">{state === "done" ? "✓" : i + 1}</span>
            <span className="bidder-step-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
