import { useEffect, useRef, useState } from "react";
import "./notifications.css";

// Same visual vocabulary VerdictBadge already uses (components.jsx) --
// success mirrors PASS's checkmark, error mirrors FAIL's cross, so a
// toast and a verdict badge never disagree about what a glyph means.
const KIND_GLYPH = { success: "✓", error: "✕", info: "ℹ" };

// Bottom-right, stacked newest-on-top (column-reverse): the conventional
// corner for a transient, non-blocking confirmation that must never cover
// primary content, a form, or the top nav.
export function ToastHost({ toasts, onDismiss }) {
  return (
    <div className="toast-host" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }) {
  // `visible` drives the CSS transition: the toast mounts hidden, then
  // flips to visible on the next frame so the browser actually animates
  // the change instead of rendering already in its final state.
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);
  const remainingRef = useRef(toast.durationMs);
  const startRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    startTimer();
    return () => {
      cancelAnimationFrame(raf);
      stopTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startTimer() {
    startRef.current = Date.now();
    timerRef.current = setTimeout(requestDismiss, remainingRef.current);
  }

  function stopTimer() {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  function requestDismiss() {
    stopTimer();
    setExiting(true);
    // The real removal happens in onTransitionEnd below, once the exit
    // transition finishes. This timeout is a safety net only, in case a
    // browser doesn't fire transitionend for a 0ms transition under
    // prefers-reduced-motion -- dismiss() on an id that's already gone is
    // a harmless no-op, so double-firing costs nothing.
    setTimeout(() => onDismiss(toast.id), 300);
  }

  function handleMouseEnter() {
    if (exiting) return;
    stopTimer();
    remainingRef.current -= Date.now() - startRef.current;
  }

  function handleMouseLeave() {
    if (exiting) return;
    if (remainingRef.current > 0) startTimer();
    else requestDismiss();
  }

  return (
    <div
      className={`toast toast-${toast.kind} ${visible && !exiting ? "toast-visible" : ""}`}
      role="status"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onTransitionEnd={(e) => {
        if (exiting && e.propertyName === "opacity") onDismiss(toast.id);
      }}
    >
      <span aria-hidden="true" className="toast-glyph">
        {KIND_GLYPH[toast.kind] || KIND_GLYPH.info}
      </span>
      <span className="toast-message">{toast.message}</span>
      <button
        type="button"
        className="toast-close"
        onClick={requestDismiss}
        aria-label="Dismiss notification"
      >
        ✕
      </button>
    </div>
  );
}
