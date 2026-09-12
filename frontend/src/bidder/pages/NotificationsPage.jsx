import { PageHeader } from "../../ui/primitives";
import { BackendPendingNotice } from "../components/BackendPendingNotice";

// No scheduler, notification table, or email/SMS sender exists in this
// backend (see bidderApi.js's getNotifications). A 30-minutes-before
// reminder or a result-published alert both need a real backend job before
// this page can show anything but this honest, empty state -- a fake
// browser setTimeout would not be a notification system, it would be a lie
// that stops working the moment the tab is closed.
export default function NotificationsPage() {
  return (
    <div className="page page-narrow" style={{ maxWidth: 680 }}>
      <PageHeader eyebrow="Bidder Portal" title="Notifications" subtitle="Alerts about your tracked tenders and results." />
      <BackendPendingNotice endpoint="GET /bidders/{bidder_id}/notifications">
        There is no notification system in this backend yet — nothing schedules or stores an alert anywhere.
        A real implementation needs a backend job to detect events (a result published, a deadline approaching)
        and a way to deliver them, neither of which exist today. This page will not simulate one with a
        browser timer.
      </BackendPendingNotice>
    </div>
  );
}
