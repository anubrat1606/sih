// Single place the backend URL is configured -- change this to match
// wherever your backend actually ends up running. No fallback/mock data
// is generated client-side if a call fails; components show the real error.
export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:4000";
export const COLLUSION_URL = import.meta.env.VITE_COLLUSION_URL || "http://localhost:8003";

export async function uploadDocument(bidderId, documentType, file) {
  const form = new FormData();
  form.append("document_type", documentType);
  form.append("file", file);
  const resp = await fetch(`${BACKEND_URL}/bidders/${encodeURIComponent(bidderId)}/documents`, {
    method: "POST",
    body: form,
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function verifyBidder(bidderId, payload) {
  const resp = await fetch(`${BACKEND_URL}/bidders/${encodeURIComponent(bidderId)}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function getTenderBidders(tenderId) {
  const resp = await fetch(`${BACKEND_URL}/tenders/${encodeURIComponent(tenderId)}/bidders`);
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function getBidder(bidderId, tenderId) {
  const url = tenderId
    ? `${BACKEND_URL}/bidders/${encodeURIComponent(bidderId)}?tender_id=${encodeURIComponent(tenderId)}`
    : `${BACKEND_URL}/bidders/${encodeURIComponent(bidderId)}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function postDecision(bidderId, tenderId, officerId, decision) {
  const resp = await fetch(`${BACKEND_URL}/bidders/${encodeURIComponent(bidderId)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ officer_id: officerId, decision, tender_id: tenderId }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function getAuditLog(bidderId) {
  const resp = await fetch(`${BACKEND_URL}/audit/${encodeURIComponent(bidderId)}`);
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function getTenderGraph(tenderId) {
  const resp = await fetch(`${COLLUSION_URL}/graph/${encodeURIComponent(tenderId)}`);
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
