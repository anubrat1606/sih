// Bidder-portal service layer -- every backend call the bidder UI makes
// goes through here, and only here, so it's auditable in one place which
// calls are real and which are not.
//
// REAL (every one of these is a real, existing orchestrator endpoint --
// confirmed against services/orchestrator/satyapramana_store/app.py before
// writing this file, not assumed). Identity/auth calls attach the bidder's
// own session token the same way api.js's setAuthToken() does for
// officers -- see setBidderToken() below.
//
// NOT IMPLEMENTED (no backend exists for these anywhere in this system --
// confirmed by reading the full route list, not assumed). Each one throws
// a BackendNotImplementedError with a plain description of exactly what
// backend capability is missing. No function here ever fabricates a
// success response -- see CLAUDE.md's non-negotiable principle, which
// applies to this portal exactly as it does to the officer one:
//   getNotifications, updateNotificationPreferences, getAuctionState,
//   submitAuctionBid.
//
// PARTIALLY CONFIGURED: continueWithGoogle() calls a real backend endpoint
// (POST /bidders/auth/google), which itself answers 503 unless an operator
// has set SATYAPRAMANA_GOOGLE_CLIENT_ID -- see GoogleSignInStatus below for
// how the frontend reports that honestly. sendMobileOtp() also calls a
// fully real endpoint that generates and stores a genuine OTP; the backend
// reports plainly (delivered: false) when no SMS provider is configured to
// actually text it to a phone -- see bidder_auth/sms_sender.py.

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

// Set by BidderSessionContext on login/signup/session restore -- kept here,
// not only in React state, because this module is the one place every
// bidder request actually leaves the browser, mirroring api.js's own
// setAuthToken() pattern for the officer portal.
let bidderToken = null;
export function setBidderToken(token) {
  bidderToken = token;
}

async function call(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (bidderToken) headers.Authorization = `Bearer ${bidderToken}`;
  const resp = await fetch(`${BACKEND_URL}${path}`, { ...options, headers });
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

// The backend returns bidder fields in snake_case (id, full_name,
// email_verified, ...); the rest of this portal was written against
// camelCase (fullName, emailVerified, ...) before this account system
// existed for real -- translated once, here, rather than touching every
// page that already reads profile.fullName etc.
function toCamelBidder(b) {
  return {
    id: b.id, email: b.email, fullName: b.full_name, mobile: b.mobile,
    companyName: b.company_name, gstin: b.gstin,
    emailVerified: b.email_verified, mobileVerified: b.mobile_verified,
    googleLinked: b.google_linked,
  };
}

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

/* ======================================================== REAL: identity */
//
// A real bidder identity table (bidder_accounts), real scrypt password
// hashing (shared with the officer side's auth/passwords.py), real email
// verification and mobile OTP flows, and a real forgot/reset password
// flow all exist on the backend now -- see satyapramana_store/bidder_auth/.

export const signUp = async ({ fullName, email, password, mobile, companyName, gstin }) => {
  const body = await call("/bidders/auth/signup", { method: "POST", ...json({
    full_name: fullName, email, password, mobile, company_name: companyName, gstin: gstin || null,
  }) });
  return { token: body.token, bidder: toCamelBidder(body.bidder), emailVerification: body.email_verification };
};

export const login = async ({ email, password }) => {
  const body = await call("/bidders/auth/login", { method: "POST", ...json({ email, password }) });
  return { token: body.token, bidder: toCamelBidder(body.bidder) };
};

export const fetchMe = async () => toCamelBidder(await call("/bidders/auth/me"));

export const sendEmailVerification = async () => {
  const body = await call("/bidders/auth/verify-email/send", { method: "POST" });
  return body.already_verified ? { delivered: true, alreadyVerified: true } : body;
};

export const confirmEmailVerification = async (token) => {
  const params = new URLSearchParams({ token });
  return toCamelBidder(await call(`/bidders/auth/verify-email/confirm?${params}`));
};

export const sendMobileOtp = async () => {
  const body = await call("/bidders/auth/verify-mobile/send", { method: "POST" });
  return body.already_verified ? { delivered: true, alreadyVerified: true } : body;
};

export const confirmMobileOtp = (otp) =>
  call("/bidders/auth/verify-mobile/confirm", { method: "POST", ...json({ otp }) });

export const forgotPassword = (email) =>
  call("/bidders/auth/forgot-password", { method: "POST", ...json({ email }) });

export const resetPassword = (token, newPassword) =>
  call("/bidders/auth/reset-password", { method: "POST", ...json({ token, new_password: newPassword }) });

export const changePassword = (currentPassword, newPassword) =>
  call("/bidders/auth/change-password", { method: "POST", ...json({
    current_password: currentPassword, new_password: newPassword,
  }) });

// Google Identity Services isn't loaded/rendered by this portal -- doing so
// only draws a real "Sign in with Google" button and produces a real ID
// token when a VITE_GOOGLE_CLIENT_ID is actually configured for this
// frontend build, matching a real SATYAPRAMANA_GOOGLE_CLIENT_ID on the
// backend. Neither is set in this deployment. Rather than render a fake
// picker or a button that does nothing when clicked, this reports the
// precise configuration gap; LoginPage renders that honestly instead of a
// working button. The backend endpoint this would call
// (POST /bidders/auth/google) is real and already answers 503 with the
// same missing-configuration detail if called directly.
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || null;

export const continueWithGoogle = (idToken) => {
  if (!GOOGLE_CLIENT_ID) {
    return notImplemented(
      "POST /bidders/auth/google",
      "Google Sign-In needs VITE_GOOGLE_CLIENT_ID configured for this frontend build and a matching " +
      "SATYAPRAMANA_GOOGLE_CLIENT_ID on the backend. Neither is set on this deployment."
    );
  }
  return call("/bidders/auth/google", { method: "POST", ...json({ id_token: idToken }) })
    .then((body) => ({ token: body.token, bidder: toCamelBidder(body.bidder) }));
};

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
