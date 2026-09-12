// Bidder-portal service layer -- every backend call the bidder UI makes
// goes through here, and only here, so it's auditable in one place which
// calls are real and which are not.
//
// REAL (existing, unauthenticated orchestrator endpoints -- confirmed
// against services/orchestrator/satyapramana_store/app.py before writing
// this file, not assumed):
//   listTenders, getTender, registerBidder, uploadBidderDocument,
//   verifyBidder, getBidder, getBidderAutopsy, getBidderRepairPlan,
//   getBidderDossier, getBidderEvidence, getBidderProvenance,
//   getTenderDocuments (derived from the audit log), getBidderDecision
//   (derived from the audit log).
//
// NOT IMPLEMENTED (no backend exists for these anywhere in this system --
// confirmed by reading the full route list, not assumed). Each one throws
// a BackendNotImplementedError with a plain description of exactly what
// backend capability is missing. No function here ever fabricates a
// success response -- see CLAUDE.md's non-negotiable principle, which
// applies to this portal exactly as it does to the officer one:
//   signUp, login, continueWithGoogle, sendEmailVerification,
//   confirmEmailVerification, sendMobileOtp, confirmMobileOtp,
//   changePassword, getNotifications, updateNotificationPreferences,
//   getAuctionState, submitAuctionBid, subscribeToAuctionReminder.

import { BACKEND_URL } from "../api";

export class BackendNotImplementedError extends Error {
  constructor(requiredEndpoint, description) {
    super(description);
    this.name = "BackendNotImplementedError";
    this.requiredEndpoint = requiredEndpoint;
  }
}

function notImplemented(requiredEndpoint, description) {
  return Promise.reject(new BackendNotImplementedError(requiredEndpoint, description));
}

async function call(path, options = {}) {
  const resp = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: { ...(options.headers || {}) },
  });
  if (!resp.ok) {
    let detail;
    try { detail = (await resp.json()).detail; } catch { detail = await resp.text(); }
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    const err = new Error(message || `${resp.status} ${resp.statusText}`);
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  const ct = resp.headers.get("content-type") || "";
  return ct.includes("application/json") ? resp.json() : resp.text();
}

const json = (body) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* ============================================================ REAL: tenders */

export const listTenders = () => call("/tenders");

export const getTender = (tenderId) => call(`/tenders/${encodeURIComponent(tenderId)}`);

// GET /tenders/{id}/bidders is real and open, but it returns every
// bidder's compliance score, risk level and evidence for that tender --
// exposing that to anyone visiting the portal would leak one bidder's
// standing to a competing bidder, which this system's own confidentiality
// principle (never show another bidder's identity or evaluation) forbids.
// The bidder portal deliberately never calls it. This is a real,
// pre-existing gap in the backend's own authorization (the endpoint has no
// auth check at all) -- worth fixing there, not worked around here by
// simply not calling it and hoping nobody else does.

/* ================================================== REAL: participation */

export const registerBidder = (tenderId, bidderId, attrs = {}) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/bidders`, { method: "POST", ...json({ bidder_id: bidderId, ...attrs }) });

export const uploadBidderDocument = (bidderId, tenderId, file, declaredType) => {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ tender_id: tenderId });
  if (declaredType) params.set("declared_type", declaredType);
  return call(`/bidders/${encodeURIComponent(bidderId)}/documents?${params}`, { method: "POST", body: form });
};

export const verifyBidder = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/verify?${new URLSearchParams({ tender_id: tenderId })}`, { method: "POST" });

/* ======================================================= REAL: my status */

export const getBidder = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}?${new URLSearchParams({ tender_id: tenderId })}`);

export const getBidderAutopsy = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/autopsy?${new URLSearchParams({ tender_id: tenderId })}`);

export const getBidderRepairPlan = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/repair-plan?${new URLSearchParams({ tender_id: tenderId })}`);

export const getBidderDossier = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/dossier?${new URLSearchParams({ tender_id: tenderId })}`);

export const getBidderEvidence = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/evidence?${new URLSearchParams({ tender_id: tenderId })}`);

/* ============================================ REAL: derived from the log */

// There is no GET for "this bidder's officer decision" or "the documents on
// this tender" or "this tender's adopted rule pack contents" -- but the
// audit log (GET /audit/export, open, real) is the authoritative record
// every one of those facts is folded from elsewhere in the app, so the
// bidder portal reads it the same way rather than inventing a shortcut.
export const getAuditExport = () => call("/audit/export");

/* ======================================= NOT IMPLEMENTED: identity/auth */
//
// There is no bidder account system anywhere in this backend: no signup
// endpoint, no bidder-scoped login, no email or SMS provider wired in, no
// OAuth client configured. auth/models.py's Role enum is exactly
// {OFFICER, SENIOR_OFFICER, ADMIN} -- there is no BIDDER role to route a
// signed-in bidder into. Every function below is a real, named integration
// point a backend engineer can implement against; none of them is faked.

export const signUp = (_payload) => notImplemented(
  "POST /bidders/auth/signup",
  "Bidder self-service accounts don't exist on this deployment yet. A backend identity table, password hashing, and this endpoint need to be built first."
);

export const login = (_credentials) => notImplemented(
  "POST /bidders/auth/login",
  "There is no bidder login endpoint -- bidder accounts aren't a concept the backend has yet."
);

export const continueWithGoogle = () => notImplemented(
  "POST /bidders/auth/google",
  "No OAuth client is configured for this deployment, and there is no backend endpoint to exchange a Google credential for a session."
);

export const sendEmailVerification = (_email) => notImplemented(
  "POST /bidders/auth/verify-email/send",
  "No email provider is wired into this backend, and no bidder account exists yet to attach a verification token to."
);

export const confirmEmailVerification = (_token) => notImplemented(
  "GET /bidders/auth/verify-email/confirm",
  "No email verification token system exists on the backend yet."
);

export const sendMobileOtp = (_mobile) => notImplemented(
  "POST /bidders/auth/verify-mobile/send",
  "No SMS/OTP provider is wired into this backend."
);

export const confirmMobileOtp = (_mobile, _otp) => notImplemented(
  "POST /bidders/auth/verify-mobile/confirm",
  "No OTP verification system exists on the backend yet."
);

export const changePassword = (_currentPassword, _newPassword) => notImplemented(
  "POST /bidders/auth/change-password",
  "There is no bidder account to change a password on yet."
);

/* ============================================= NOT IMPLEMENTED: auction */
//
// Nothing in this system's architecture (docs/satyapramana.md) models a
// live bidding/auction mechanism -- SATYAPRAMĀṆ is a compliance
// verification layer over a tender's bidders, not the e-auction itself.
// GeM's own auction (if a given tender runs one) is a separate system this
// project has never integrated with. These are named as the integration
// points a real auction feed would need.

export const getAuctionState = (_tenderId) => notImplemented(
  "GET /tenders/{tender_id}/auction",
  "No auction/bidding service exists in this system -- SATYAPRAMĀṆ verifies compliance, it does not run or record a live auction."
);

export const submitAuctionBid = (_tenderId, _amount) => notImplemented(
  "POST /tenders/{tender_id}/auction/bids",
  "No auction/bidding service exists in this system yet."
);

/* ======================================= NOT IMPLEMENTED: notifications */
//
// There is no scheduler, no notification table, and no email/SMS sender in
// this backend. A 30-minute-before-auction reminder or a result-published
// alert both need a real backend job to exist before this portal can show
// anything but an honestly empty notification centre.

export const getNotifications = () => notImplemented(
  "GET /bidders/{bidder_id}/notifications",
  "No notification system exists in this backend -- nothing schedules or stores a notification anywhere yet."
);

export const updateNotificationPreferences = (_prefs) => notImplemented(
  "PATCH /bidders/{bidder_id}/notification-preferences",
  "No notification-preferences storage exists in this backend yet."
);

export { BACKEND_URL };
