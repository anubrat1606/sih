// End-to-end smoke test against the real running stack.
// Requires: extraction (8001), verification (8002), collusion (8003),
// backend (4000) all running, and MongoDB reachable by the backend.
//
// This test uses real document images and real bidder identities you
// supply -- it does not generate or embed any synthetic data itself.
// Run: node scripts/e2e_test.js
//
// Fill these in before running:
const TENDER_ID = "REPLACE_WITH_REAL_TENDER_ID";
const BIDDERS = [
  // A and B should be two REAL, consenting registrations that genuinely
  // share an attribute (e.g. same phone/address) -- see the conversation
  // notes on why this should be real, not invented, data.
  { bidder_id: "REPLACE_A", document_type: "PAN", file_path: "REPLACE_WITH_REAL_IMAGE_PATH",
    director_name: "REPLACE", address: "REPLACE", phone: "REPLACE_SHARED", bank_account: "REPLACE" },
  { bidder_id: "REPLACE_B", document_type: "PAN", file_path: "REPLACE_WITH_REAL_IMAGE_PATH",
    director_name: "REPLACE_DIFFERENT", address: "REPLACE_DIFFERENT", phone: "REPLACE_SHARED", bank_account: "REPLACE_DIFFERENT" },
  { bidder_id: "REPLACE_C", document_type: "PAN", file_path: "REPLACE_WITH_REAL_IMAGE_PATH",
    director_name: "REPLACE_UNRELATED", address: "REPLACE_UNRELATED", phone: "REPLACE_UNRELATED", bank_account: "REPLACE_UNRELATED" },
];
const BACKEND_URL = "http://localhost:4000";

import fs from "node:fs";
import FormData from "form-data";
import fetch from "node-fetch";

function assert(cond, msg) {
  console.log(cond ? `PASS: ${msg}` : `FAIL: ${msg}`);
  return cond;
}

async function run() {
  if (TENDER_ID.startsWith("REPLACE")) {
    console.error("Fill in TENDER_ID and BIDDERS with real values before running this script.");
    process.exit(1);
  }

  for (const b of BIDDERS) {
    const form = new FormData();
    form.append("document_type", b.document_type);
    form.append("file", fs.createReadStream(b.file_path));
    const uploadResp = await fetch(`${BACKEND_URL}/bidders/${b.bidder_id}/documents`, { method: "POST", body: form });
    if (!uploadResp.ok) throw new Error(`Upload failed for ${b.bidder_id}: ${await uploadResp.text()}`);

    const verifyResp = await fetch(`${BACKEND_URL}/bidders/${b.bidder_id}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tender_id: TENDER_ID,
        director_name: b.director_name,
        address: b.address,
        phone: b.phone,
        bank_account: b.bank_account,
      }),
    });
    if (!verifyResp.ok) throw new Error(`Verify failed for ${b.bidder_id}: ${await verifyResp.text()}`);
  }

  const listResp = await fetch(`${BACKEND_URL}/tenders/${TENDER_ID}/bidders`);
  const scores = await listResp.json();
  console.log(JSON.stringify(scores, null, 2));

  const [a, b, c] = BIDDERS;
  const scoreA = scores.find((s) => s.bidder_id === a.bidder_id);
  const scoreB = scores.find((s) => s.bidder_id === b.bidder_id);
  const scoreC = scores.find((s) => s.bidder_id === c.bidder_id);

  assert(scoreA?.collusion_flag?.flagged, `${a.bidder_id} flagged for collusion`);
  assert(scoreB?.collusion_flag?.flagged, `${b.bidder_id} flagged for collusion`);
  assert(!scoreC?.collusion_flag?.flagged, `${c.bidder_id} NOT flagged (unrelated bidder)`);

  const decisionResp = await fetch(`${BACKEND_URL}/bidders/${a.bidder_id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ officer_id: "officer_demo", decision: "DISQUALIFY", tender_id: TENDER_ID }),
  });
  assert(decisionResp.ok, "decision recorded");

  const auditResp = await fetch(`${BACKEND_URL}/audit/${a.bidder_id}`);
  const auditEntries = await auditResp.json();
  assert(auditEntries.length >= 1, "audit log has at least one entry");
  assert(auditEntries[0].prev_hash === "genesis" || auditEntries.length > 1, "hash chain starts correctly");
}

run().catch((err) => {
  console.error("E2E TEST FAILED:", err);
  process.exit(1);
});
