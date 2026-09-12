// Split out of NotificationBell.jsx so that file can export only the
// component (Fast Refresh only works when a file exports nothing but
// components -- the same reason theme.js/components.jsx and
// authContext.js/auth.jsx are split the same way elsewhere in this app).
const LAST_SEEN_KEY = "satyapramana-bidder-notifications-last-seen";

export function readLastSeen() {
  try {
    const raw = localStorage.getItem(LAST_SEEN_KEY);
    return raw ? new Date(raw) : null;
  } catch {
    return null; // private browsing / storage blocked -- badge just won't clear
  }
}

// Call when NotificationsPage.jsx has been viewed, so the badge count
// drops on the next render elsewhere in the app.
export function markNotificationsSeen() {
  try {
    localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
  } catch { /* private browsing / storage blocked */ }
}
