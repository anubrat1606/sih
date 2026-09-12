// Single place the backend URL is configured. Every function here calls the
// real satyapramana_store orchestrator -- no client-side fallback or mock
// value is ever generated when a call fails; callers show the real error.
export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:4000";

// Set by auth.js's AuthProvider on login/logout/session restore -- kept
// here, not in a React context, because api.js is the one place every
// request actually leaves the browser, and a module-level value is the
// simplest thing that can be read synchronously from a plain function.
let authToken = null;

// For the two places that can't go through call(): pdf.js fetches the PDF
// itself (it accepts httpHeaders), and "View source" opens the raw file --
// GET /documents/{sha} requires a login now, so a bare <a href> would 401.
export function authHeaders() {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

export async function openDocument(sha256) {
  const resp = await fetch(`${BACKEND_URL}/documents/${encodeURIComponent(sha256)}`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`could not fetch document (${resp.status})`);
  const url = URL.createObjectURL(await resp.blob());
  window.open(url, "_blank", "noopener");
}
export function setAuthToken(token) {
  authToken = token;
}

// Exported so bidder/bidderApi.js can reuse this exact fetch wrapper
// (auth header, error shape, JSON/text negotiation) instead of a second
// hand-rolled copy of it.
export async function call(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const resp = await fetch(`${BACKEND_URL}${path}`, { ...options, headers });
  if (!resp.ok) {
    let detail;
    try {
      detail = (await resp.json()).detail;
    } catch {
      detail = await resp.text();
    }
    // `detail` can be a plain string or a structured object (e.g. rule pack
    // adoption returns {error, violations[]}) -- callers that care about the
    // structure read err.detail directly; ErrorBox falls back to JSON.
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    const err = new Error(message || `${resp.status} ${resp.statusText}`);
    err.detail = detail;
    throw err;
  }
  const contentType = resp.headers.get("content-type") || "";
  return contentType.includes("application/json") ? resp.json() : resp.text();
}

const json = (body) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const getCapabilities = () => call("/capabilities");

export const getDashboard = () => call("/dashboard");

export const login = (username, password) =>
  call("/auth/login", { method: "POST", ...json({ username, password }) });

export const getMe = () => call("/auth/me");

export const createOfficerAccount = (username, password, displayName, role) =>
  call("/auth/users", { method: "POST",
    ...json({ username, password, display_name: displayName, role }) });

export const listTenders = () => call("/tenders");

export const createTender = (tenderId, title, issuingAuthority, bidSubmissionDeadline, description,
  extra = {}) =>
  call("/tenders", { method: "POST", ...json({
    tender_id: tenderId, title, issuing_authority: issuingAuthority,
    bid_submission_deadline: bidSubmissionDeadline || null, description: description || null,
    department: extra.department || null, category: extra.category || null,
    issue_date: extra.issueDate || null,
  }) });

export const uploadTenderDocument = (tenderId, file) => {
  const form = new FormData();
  form.append("file", file);
  return call(`/tenders/${encodeURIComponent(tenderId)}/documents`, { method: "POST", body: form });
};

export const getRequirementTypes = () => call("/requirement-types");

export const validateRulePack = (tenderId, pack) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/rule-pack/validate`, { method: "POST", ...json({ pack }) });

export const getTender = (tenderId) => call(`/tenders/${encodeURIComponent(tenderId)}`);

export const registerBidder = (tenderId, bidderId, attrs) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/bidders`, { method: "POST", ...json({ bidder_id: bidderId, ...attrs }) });

export const uploadDocument = (bidderId, tenderId, file, declaredType) => {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ tender_id: tenderId });
  if (declaredType) params.set("declared_type", declaredType);
  return call(`/bidders/${encodeURIComponent(bidderId)}/documents?${params}`, { method: "POST", body: form });
};

export const verifyBidder = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/verify?${new URLSearchParams({ tender_id: tenderId })}`, { method: "POST" });

export const adoptRulePack = (tenderId, pack) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/rule-pack`, { method: "POST", ...json({ pack }) });

export const evaluateBidder = (bidderId, tenderId, bidSubmissionDate, asOf) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/evaluate?${new URLSearchParams({ tender_id: tenderId })}`, {
    method: "POST", ...json({ bid_submission_date: bidSubmissionDate, as_of: asOf || null }),
  });

export const listTenderBidders = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/bidders`);

export const getBidder = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}?${new URLSearchParams({ tender_id: tenderId })}`);

export const getProvenance = (bidderId, requirementId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/requirements/${encodeURIComponent(requirementId)}/provenance`);

export const getTenderCollusion = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/collusion`);

export const getCollusionEdges = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/collusion/edges`);

export const recordDecision = (bidderId, tenderId, decision, note) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/decision?${new URLSearchParams({ tender_id: tenderId })}`, {
    method: "POST", ...json({ decision, note: note || null }),
  });

export const overrideVerdict = (bidderId, tenderId, requirementId, verdictAfter, justification) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/override?${new URLSearchParams({ tender_id: tenderId })}`, {
    method: "POST",
    ...json({ requirement_id: requirementId, verdict_after: verdictAfter, justification }),
  });

export const getAutopsy = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/autopsy?${new URLSearchParams({ tender_id: tenderId })}`);

export const getBidderEvidence = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/evidence?${new URLSearchParams({ tender_id: tenderId })}`);

export const getBidderEvidenceGraph = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/evidence-graph?${new URLSearchParams({ tender_id: tenderId })}`);

export const getRepairPlan = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/repair-plan?${new URLSearchParams({ tender_id: tenderId })}`);

export const getExplanation = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/explain?${new URLSearchParams({ tender_id: tenderId })}`);

export const decomposeTender = (tenderId, documentSha256) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/decompose`, { method: "POST",
    ...json({ document_sha256: documentSha256 }) });

export const getAuditExport = () => call("/audit/export");
export const getAuditVerify = () => call("/audit/verify");

// The Compliance Dossier and the tender-wide JSON report: both live backend
// features that had no frontend caller at all before the Reports area.
export const getBidderDossier = (bidderId, tenderId) =>
  call(`/bidders/${encodeURIComponent(bidderId)}/dossier?${new URLSearchParams({ tender_id: tenderId })}`);

export const getTenderReport = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/report`);

export const getTenderReportCsv = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/report/csv`);

export const getTenderBlockers = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/blockers`);
