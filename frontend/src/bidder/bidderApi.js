// The bidder-facing service layer. One function per backend endpoint that
// actually exists (services/orchestrator/satyapramana_store/app.py's
// "bidder self-service" section) -- reuses api.js's call() for the fetch
// wrapper, auth header, and error shape rather than duplicating it.
//
// Rishika, Suhani, and Kevin's pages import from here, never from api.js
// directly and never by constructing a URL themselves. If a page needs
// something not exported here, that's a policy question (see
// docs/NEXT_TASKS_6_anubrat_rishika_suhani_kevin.md's bidder-visible-data
// table), not something to work around locally.
import { call, json } from "../api";

/**
 * @typedef {Object} MyTender
 * @property {string} tender_id
 * @property {string|null} title
 * @property {string|null} issuing_authority
 * @property {string|null} bid_submission_deadline
 * @property {string|null} description
 * @property {string|null} department
 * @property {string|null} category
 * @property {string|null} issue_date
 * @property {boolean} requirements_published
 * @property {boolean} registered
 * @property {"NOT_REGISTERED"|"REGISTERED"|"DOCUMENTS_RECEIVED"|"UNDER_EVALUATION"|"DECIDED"} status
 */
/** @returns {Promise<{tenders: MyTender[]}>} */
export const getMyTenders = () => call("/me/tenders");

/**
 * @typedef {Object} MyRequirement
 * @property {string} id
 * @property {string} text
 * @property {"mandatory"|"desirable"} obligation
 * @property {number|null} source_page
 * @property {string} evidence_expected
 */
/** @returns {Promise<{tender_id: string, requirements: MyRequirement[]}>} */
export const getMyTenderRequirements = (tenderId) =>
  call(`/me/tenders/${encodeURIComponent(tenderId)}/requirements`);

/**
 * @typedef {Object} MyDeclaration
 * @property {string} requirement_id
 * @property {string} declaration_text
 * @property {string} declared_by
 * @property {string} declared_at
 */
/**
 * @returns {Promise<{tender_id: string, bidder_id: string, status: string,
 *   documents: object[], declarations: MyDeclaration[]}>}
 * Each entry in `documents` is exactly what POST /bidders/{id}/documents
 * returned at upload time (document_sha256, extracted[], rejected[],
 * unreadable_pages[], identifier_cross_check) -- read back from the event
 * log, not re-derived. `declarations` (round 9) is one row per requirement
 * this bidder has recorded a self-declaration for -- a correction replaces
 * the row, never appends a second one for the same requirement.
 */
export const getMySubmission = (tenderId) =>
  call(`/me/tenders/${encodeURIComponent(tenderId)}/submission`);

/**
 * Record a self-declaration / undertaking for one requirement -- round 9's
 * answer to the one requirement type that was never an extraction problem:
 * an undertaking IS the self-declaration, captured as a real, attributed
 * event, never a document to parse.
 * @returns {Promise<{bidder_id: string, tender_id: string, requirement_id: string,
 *   declared_by: string, seq: number}>}
 */
export const recordDeclaration = (bidderId, tenderId, requirementId, declarationText) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/declarations?${new URLSearchParams({ tender_id: tenderId })}`, {
    method: "POST",
    ...json({ requirement_id: requirementId, declaration_text: declarationText }),
  });

/**
 * @returns {Promise<
 *   {tender_id: string, bidder_id: string, published: false} |
 *   {tender_id: string, bidder_id: string, published: true, decision: "QUALIFY"|"DISQUALIFY",
 *    decided_at: string, note: string|null,
 *    outcomes: {requirement_id: string, verdict: "PASS"|"FAIL"|"PARTIAL"|"UNKNOWN"}[],
 *    repair_actions: object[]}
 * >}
 */
export const getMyResult = (tenderId) =>
  call(`/me/tenders/${encodeURIComponent(tenderId)}/result`);

/**
 * Upload one of the signed-in bidder's own documents. Same endpoint and
 * same response shape the officer page uses -- the extraction summary in
 * the response IS what SubmitDocumentsPage renders, not a second call.
 * @returns {Promise<{document_sha256: string, pages: number, extracted: object[],
 *   rejected: object[], unreadable_pages: object[], identifier_cross_check: object|null}>}
 */
export const uploadMyDocument = (bidderId, tenderId, file, declaredType) => {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ tender_id: tenderId });
  if (declaredType) params.set("declared_type", declaredType);
  return call(`/bidders/${encodeURIComponent(bidderId)}/documents?${params}`, {
    method: "POST", body: form,
  });
};

/**
 * Round 10. Starts a real DigiLocker consent flow -- the returned
 * authorization_url is where the bidder's own browser must go next (not an
 * iframe, not a background call: DigiLocker requires the bidder to
 * authenticate directly with their own Aadhaar-linked mobile OTP). Nothing
 * is verified yet at this point, only requested.
 * @returns {Promise<{bidder_id: string, tender_id: string, session_id: string, authorization_url: string}>}
 */
export const startDigilockerSession = (bidderId, tenderId, redirectUrl) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/digilocker/session?${new URLSearchParams({ tender_id: tenderId })}`, {
    method: "POST",
    ...json({ redirect_url: redirectUrl }),
  });

/**
 * Polled after the bidder returns from DigiLocker's own consent screen.
 * `status: "created"` means still pending -- poll again. `"succeeded"`
 * means the backend already fetched the document and recorded a real
 * verification event; `"failed"`/`"expired"` means the bidder declined or
 * the session timed out, also already recorded.
 * @returns {Promise<{status: "created"} |
 *   {status: "failed"|"expired", verdict: string} |
 *   {status: "succeeded", document_fetch: "ok"|"failed", issuer?: string, description?: string}>}
 */
export const getDigilockerStatus = (bidderId, tenderId, sessionId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/digilocker/status?${new URLSearchParams({ tender_id: tenderId, session_id: sessionId })}`);

// --- not yet real on this deployment ------------------------------------
//
// Named backend dependencies, not faked successes. Every one of these
// throws or resolves to { available: false, reason }; no caller may treat
// that as a green state. See NEXT_TASKS_6's "decisions this round takes":
// no scheduler, no email/SMS provider exists to back these yet.

/** @returns {Promise<{available: false, reason: string}>} */
export const getScheduledNotifications = async () => ({
  available: false,
  reason: "no notification scheduler on this deployment",
});
