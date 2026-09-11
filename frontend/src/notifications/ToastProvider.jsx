import { useCallback, useState } from "react";
import { ToastContext } from "./ToastContext";
import { ToastHost } from "./ToastHost";

let nextId = 0;

// Wrap <App> in this once. Every action handler that wants to confirm
// success or report a failure calls useToast().notify(...) from anywhere
// in the tree -- no prop drilling, no per-page toast state.
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback((message, { kind = "info", durationMs = 4000 } = {}) => {
    const id = ++nextId;
    setToasts((prev) => [...prev, { id, message, kind, durationMs }]);
    return id;
  }, []);

  return (
    <ToastContext.Provider value={{ notify, dismiss }}>
      {children}
      <ToastHost toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}
