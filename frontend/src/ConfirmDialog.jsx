import { useEffect, useId, useRef } from "react";
import "./confirmDialog.css";

// Generic yes/no confirmation, not hardcoded to any one action -- Phase 7
// wires this into both the Disqualify decision button and the officer
// Override action, both of which currently fire immediately with no
// confirmation at all.
//
// `open` fully controls mount/visibility; this component never manages its
// own open state. `onConfirm`/`onCancel` are called, and the caller closes
// the dialog by flipping `open` to false.
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const triggerRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;

    // The safer default when a real destructive action is one Enter-key
    // press away: focus starts on Cancel, never on Confirm.
    triggerRef.current = document.activeElement;
    cancelRef.current?.focus();

    function handleKeyDown(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCancel();
        return;
      }
      if (e.key !== "Tab") return;
      const focusables = dialogRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables || focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      // Trap focus: Tab past the last element wraps to the first, and
      // Shift+Tab past the first wraps to the last -- it never escapes to
      // the page behind the dialog.
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      // Return focus to whatever triggered the dialog.
      triggerRef.current?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="confirm-dialog-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div ref={dialogRef} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <h2 id={titleId} className="confirm-dialog-title">{title}</h2>
        {body && <div className="confirm-dialog-body">{body}</div>}
        <div className="confirm-dialog-actions">
          <button type="button" ref={cancelRef} className="confirm-dialog-cancel" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className={danger ? "danger" : ""} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
