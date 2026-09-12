// Turns the bidder-scoped API responses into a flat, sorted notification
// list. loadNotificationSource() is the one place that fetches them --
// moved here during A6 integration so both NotificationsPage.jsx and
// BidderShell.jsx's NotificationBell (which needs a live count on every
// page, not just this one) share a single fetch implementation instead of
// two copies drifting apart.
import { getMyResult, getMySubmission, getMyTenders } from "../bidderApi";
// Nothing here is delivered: there is no scheduler and no email/SMS
// provider on this deployment (see bidderApi.js's getScheduledNotifications
// and NotificationsPage.jsx). Every entry restates a fact the backend
// already returned -- registered, a document was ingested, a decision was
// recorded -- it does not invent a new one.
//
// Two of the four kinds below have no real timestamp anywhere in the
// bidder-scoped API today: GET /me/tenders returns `requirements_published`
// as a bare boolean with no adoption date, and GET /me/tenders/{id}/
// submission returns each document's extraction payload
// (document_sha256, storage_ref, filename, declared_type, bytes) with no
// occurred_at -- confirmed by reading app.py's my_submission handler and
// extract/ingest.py's DOCUMENT_INGESTED payload directly, not assumed.
// Rather than inventing a timestamp, those entries carry `at: null` and
// NotificationsPage.jsx groups them under an honest "no timestamp
// recorded" heading instead of a fabricated date -- the same "null, never
// a fake zero" rule this project applies to every other metric.

const DAY_MS = 24 * 60 * 60 * 1000;
const DEADLINE_WARNING_DAYS = 7;

/**
 * @param {{tenders: import("../bidderApi").MyTender[]}} myTenders
 * @param {Record<string, {tender_id:string, bidder_id:string, status:string, documents:object[]}>} submissionsByTender
 *   Keyed by tender_id. Pass only tenders the caller already fetched a
 *   submission for (i.e. ones the bidder is registered on).
 * @param {Record<string, object>} resultsByTender
 *   Keyed by tender_id, each the raw getMyResult() response.
 * @param {Date} [now] Injectable for tests; defaults to the real current time.
 * @returns {{kind: "requirements_published"|"deadline_approaching"|"document_received"|"decision_recorded",
 *   tender_id: string, title: string, at: string|null, to: string}[]}
 */
export function deriveNotifications(myTenders, submissionsByTender = {}, resultsByTender = {}, now = new Date()) {
  const tenders = myTenders?.tenders || [];
  const items = [];

  for (const t of tenders) {
    // Only tenders the bidder is actually registered on generate
    // notifications -- "requirements published" for every discoverable
    // tender on the platform is TendersPage's job (browsing), not a
    // per-bidder notification.
    if (!t.registered) continue;
    const title = t.title || t.tender_id;
    const tenderTo = `/portal/tenders/${encodeURIComponent(t.tender_id)}`;

    if (t.requirements_published) {
      items.push({
        kind: "requirements_published", tender_id: t.tender_id,
        title: `Requirements published for ${title}`, at: null, to: tenderTo,
      });
    }

    if (t.bid_submission_deadline) {
      const deadline = new Date(t.bid_submission_deadline);
      if (!Number.isNaN(deadline.getTime())) {
        const daysLeft = (deadline.getTime() - now.getTime()) / DAY_MS;
        if (daysLeft >= 0 && daysLeft <= DEADLINE_WARNING_DAYS) {
          items.push({
            kind: "deadline_approaching", tender_id: t.tender_id,
            title: `Deadline approaching for ${title}`, at: t.bid_submission_deadline, to: tenderTo,
          });
        }
      }
    }

    const submission = submissionsByTender[t.tender_id];
    for (const doc of submission?.documents || []) {
      items.push({
        kind: "document_received", tender_id: t.tender_id,
        title: `${doc.filename || "A document"} received for ${title}`,
        at: null, to: "/portal/submissions",
      });
    }

    const result = resultsByTender[t.tender_id];
    if (result?.published) {
      items.push({
        kind: "decision_recorded", tender_id: t.tender_id,
        title: `Decision recorded for ${title}`, at: result.decided_at, to: "/portal/results",
      });
    }
  }

  // Real-timestamp entries sorted newest first; undated entries keep the
  // order they were derived in (tender list order) and are placed after
  // every dated entry rather than interleaved as if they had a position
  // in time they don't actually have.
  const dated = items.filter((i) => i.at).sort((a, b) => new Date(b.at) - new Date(a.at));
  const undated = items.filter((i) => !i.at);
  return [...dated, ...undated];
}

// Fetches exactly what deriveNotifications() needs and nothing more --
// getMySubmission/getMyResult only for tenders this bidder is actually
// registered on, since those endpoints are scoped to the caller's own
// bidder_id and there is nothing to ask for on a tender not yet joined.
export async function loadNotificationSource() {
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
