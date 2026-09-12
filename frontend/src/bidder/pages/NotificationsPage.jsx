import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { getMyResult, getMySubmission, getMyTenders, getScheduledNotifications } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, UnavailableNote } from "../../ui/primitives";
import { deriveNotifications } from "../notifications/deriveNotifications";
import { markNotificationsSeen } from "../notifications/NotificationBell";

const KIND_GLYPH = {
  requirements_published: "▤",
  deadline_approaching: "◔",
  document_received: "▥",
  decision_recorded: "✓",
};

// Fetches exactly what deriveNotifications.js needs and nothing more --
// getMySubmission/getMyResult only for tenders this bidder is actually
// registered on, since those endpoints are scoped to the caller's own
// bidder_id and there is nothing to ask for on a tender not yet joined.
async function loadNotificationSource() {
  const myTenders = await getMyTenders();
  const registered = (myTenders.tenders || []).filter((t) => t.registered);
  const [submissions, results] = await Promise.all([
    Promise.all(registered.map((t) => getMySubmission(t.tender_id))),
    Promise.all(registered.map((t) => getMyResult(t.tender_id))),
  ]);
  const submissionsByTender = {};
  const resultsByTender = {};
  registered.forEach((t, i) => {
    submissionsByTender[t.tender_id] = submissions[i];
    resultsByTender[t.tender_id] = results[i];
  });
  return { myTenders, submissionsByTender, resultsByTender };
}

function formatDayLabel(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

// Groups an already-sorted (dated-first, newest-first) notification list
// into day buckets, with every undated entry (see deriveNotifications.js)
// collected under one honest "no timestamp recorded" bucket rather than
// scattered under a fabricated date.
function groupByDay(items) {
  const groups = [];
  let currentKey = null;
  for (const item of items) {
    const key = item.at ? new Date(item.at).toDateString() : "__no_timestamp__";
    if (key !== currentKey) {
      groups.push({ key, label: item.at ? formatDayLabel(item.at) : "No timestamp recorded", items: [] });
      currentKey = key;
    }
    groups[groups.length - 1].items.push(item);
  }
  return groups;
}

export default function NotificationsPage() {
  const source = useApi(() => loadNotificationSource(), []);
  const scheduled = useApi(() => getScheduledNotifications(), []);

  const notifications = useMemo(() => {
    if (!source.data) return [];
    return deriveNotifications(source.data.myTenders, source.data.submissionsByTender, source.data.resultsByTender);
  }, [source.data]);

  const groups = useMemo(() => groupByDay(notifications), [notifications]);

  // Viewing this page is the one real "seen" signal this deployment has --
  // a per-browser convenience for NotificationBell's badge count, never
  // reported anywhere else.
  useEffect(() => {
    if (source.data) markNotificationsSeen();
  }, [source.data]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder Portal"
        title="Notifications"
        subtitle="Every entry below restates something already true in the system — nothing here is a separately delivered message."
      />

      <ErrorState error={source.error} onRetry={source.reload} />

      {source.loading ? (
        <LoadingBlock lines={4} />
      ) : notifications.length === 0 ? (
        <EmptyState glyph="◔" title="No notifications"
                    message="You'll see updates here once you're registered on a tender." />
      ) : (
        <div className="stack" style={{ gap: 20 }}>
          {groups.map((group) => (
            <Card key={group.key} title={group.label}>
              <div className="stack-sm">
                {group.items.map((n, i) => (
                  <Link key={`${n.kind}-${n.tender_id}-${i}`} to={n.to} className="row"
                        style={{ gap: 10, textDecoration: "none", color: "inherit" }}>
                    <span aria-hidden="true">{KIND_GLYPH[n.kind] || "•"}</span>
                    <span className="text-sm">{n.title}</span>
                  </Link>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      {!scheduled.loading && scheduled.data && scheduled.data.available === false && (
        <div style={{ marginTop: 20 }}>
          <UnavailableNote title="Scheduled reminders and email">
            {scheduled.data.reason}. There are no scheduled reminders and no emails on this deployment —
            everything above is derived live from your account each time you open this page.
          </UnavailableNote>
        </div>
      )}

      <div style={{ marginTop: 20 }}>
        <Card title="Notification preferences">
          <div className="stack-sm">
            {["Tender updates", "Deadline reminders", "Decision notifications"].map((label) => (
              <div key={label} className="row" style={{ justifyContent: "space-between" }}>
                <span className="text-sm">{label}</span>
                <span className="text-xs text-muted">Not available on this deployment</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
