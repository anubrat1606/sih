import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

// A header control showing how many derived notifications are newer than
// this browser's own "last seen" mark. Per-browser convenience only --
// never treated as real state, wrapped in try/catch, and never counted
// against anything the backend tracks, because there is nothing for the
// backend to track: no notification store exists on this deployment (see
// bidderApi.js's getScheduledNotifications). Mounted in BidderShell.jsx's
// topbar (Anubrat's file); this file only exports the pieces.

const LAST_SEEN_KEY = "satyapramana-bidder-notifications-last-seen";

function readLastSeen() {
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

/**
 * @param {{notifications: {at: string|null}[]}} props
 *   The same list NotificationsPage.jsx derives and renders -- passed in,
 *   not re-fetched here, so there is exactly one place that calls the
 *   bidder-scoped endpoints for this data.
 */
export function NotificationBell({ notifications }) {
  const [lastSeen, setLastSeen] = useState(readLastSeen);

  // Re-read on every render of the list this prop represents, so signing
  // out/in or viewing the notifications page in another tab is reflected
  // without this component needing its own fetch.
  useEffect(() => {
    setLastSeen(readLastSeen());
  }, [notifications]);

  // An entry with no timestamp (see deriveNotifications.js) has no way to
  // be compared against "last seen" -- counted as unseen until the list is
  // actually viewed, same as any entry newer than the mark.
  const unseenCount = notifications.filter((n) => !n.at || !lastSeen || new Date(n.at) > lastSeen).length;

  return (
    <Link to="/portal/notifications" className="topbar-button"
          aria-label={unseenCount > 0 ? `Notifications (${unseenCount} new)` : "Notifications"}>
      <span aria-hidden="true">◔</span>
      {unseenCount > 0 && <span className="topbar-badge-count">{unseenCount}</span>}
    </Link>
  );
}
