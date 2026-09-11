import { useContext } from "react";
import { ToastContext } from "./ToastContext";

// notify(message, { kind = "info", durationMs = 4000 } = {}) queues a toast
//   and returns its id.
// dismiss(id) removes one early -- used by a toast's own close button, and
//   available to callers that want to withdraw a notification programmatically
//   (e.g. an in-flight "Uploading…" toast replaced by a "Done" one).
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // A silent no-op here would hide a real wiring mistake behind "nothing
    // happened" -- exactly the kind of fabricated success this project
    // refuses everywhere else. Fail loud instead.
    throw new Error(
      "useToast() was called outside a <ToastProvider>. Wrap the part of " +
      "the app that needs notifications in <ToastProvider> from " +
      "\"./notifications\"."
    );
  }
  return ctx;
}
