import { Link } from "react-router-dom";
import { readLastSeen } from "./lastSeen";

// A header control showing how many derived notifications are newer than
// this browser's own "last seen" mark. Per-browser convenience only --
// never treated as real state, wrapped in try/catch, and never counted
// against anything the backend tracks, because there is nothing for the
// backend to track: no notification store exists on this deployment (see
// bidderApi.js's getScheduledNotifications). Mounted in BidderShell.jsx's
// topbar (Anubrat's file); this file only exports the component.

/**
 * @param {{notifications: {at: string|null}[]}} props
 *   The same list NotificationsPage.jsx derives and renders -- passed in,
 *   not re-fetched here, so there is exactly one place that calls the
 *   bidder-scoped endpoints for this data.
 */
export function NotificationBell({ notifications }) {
  // readLastSeen() is a cheap, synchronous localStorage read -- derived
  // directly during render (not useState+useEffect) so it's naturally
  // re-read on every re-render this prop already causes, with no separate
  // effect needed to keep it in sync.
  const lastSeen = readLastSeen();

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
