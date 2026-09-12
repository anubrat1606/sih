import { useState } from "react";

const STORAGE_KEY = "satyapramana-theme";

// "system" leaves <html> unstamped so prefers-color-scheme decides; an
// explicit choice stamps data-theme, which tokens.css treats as final.
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || "system"; } catch { return "system"; }
  });
  function apply(next) {
    setTheme(next);
    if (next === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* storage blocked */ }
  }
  return [theme, apply];
}
