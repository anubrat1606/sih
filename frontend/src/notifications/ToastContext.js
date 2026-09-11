import { createContext } from "react";

// Split into its own file so ToastProvider.jsx only exports the component
// (Fast Refresh needs that) and ToastHost/useToast can each import the
// context without importing one another.
export const ToastContext = createContext(null);
