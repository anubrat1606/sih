import "dotenv/config";
import crypto from "node:crypto";
import express from "express";
import cors from "cors";
import multer from "multer";
import mongoose from "mongoose";
import fetch from "node-fetch";
import FormData from "form-data";
import { Extraction, Score, AuditLog } from "./models.js";

const app = express();
app.use(cors());
app.use(express.json());

const upload = multer({ storage: multer.memoryStorage() });

const PORT = process.env.PORT || 4000;
const MONGODB_URI = process.env.MONGODB_URI || "mongodb://localhost:27017/sih26100";
const EXTRACTION_URL = process.env.EXTRACTION_SERVICE_URL || "http://localhost:8001";
const VERIFICATION_URL = process.env.VERIFICATION_SERVICE_URL || "http://localhost:8002";
const COLLUSION_URL = process.env.COLLUSION_SERVICE_URL || "http://localhost:8003";

function riskLevelFor(score) {
  if (score >= 80) return "LOW";
  if (score >= 50) return "MEDIUM";
  return "HIGH";
}

function sha256(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

// --- Upload + extract -------------------------------------------------

app.post("/bidders/:bidderId/documents", upload.single("file"), async (req, res) => {
  const { bidderId } = req.params;
  const { document_type: documentType } = req.body;
  if (!req.file) return res.status(400).json({ error: "file is required" });
  if (!documentType) return res.status(400).json({ error: "document_type is required" });

  try {
    const form = new FormData();
    form.append("bidder_id", bidderId);
    form.append("document_type", documentType);
    form.append("file", req.file.buffer, { filename: req.file.originalname });

    const extractResp = await fetch(`${EXTRACTION_URL}/extract`, { method: "POST", body: form });
    if (!extractResp.ok) {
      const errText = await extractResp.text();
      return res.status(502).json({ error: "extraction service failed", details: errText });
    }
    const extraction = await extractResp.json();

    await Extraction.findOneAndUpdate(
      { bidder_id: bidderId, document_type: documentType },
      extraction,
      { upsert: true, new: true }
    );

    res.json(extraction);
  } catch (err) {
    res.status(500).json({ error: "orchestration failure", details: String(err) });
  }
});

// --- Verify + collusion check ------------------------------------------

app.post("/bidders/:bidderId/verify", async (req, res) => {
  const { bidderId } = req.params;
  const { tender_id: tenderId, director_name, address, phone, bank_account } = req.body || {};
  if (!tenderId) return res.status(400).json({ error: "tender_id is required in body" });

  try {
    const extractionDocs = await Extraction.find({ bidder_id: bidderId });
    if (extractionDocs.length === 0) {
      return res.status(404).json({ error: "no extracted documents found for this bidder yet" });
    }

    let allChecks = [];
    let scoreSum = 0;
    for (const doc of extractionDocs) {
      const verifyResp = await fetch(`${VERIFICATION_URL}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bidder_id: bidderId,
          document_type: doc.document_type,
          extracted_fields: doc.extracted_fields,
          confidence: doc.confidence,
          raw_ocr_text: doc.raw_ocr_text,
          source_s3_key: doc.source_s3_key,
        }),
      });
      if (!verifyResp.ok) {
        const errText = await verifyResp.text();
        return res.status(502).json({ error: "verification service failed", details: errText });
      }
      const result = await verifyResp.json();
      allChecks = allChecks.concat(result.checks);
      scoreSum += result.sub_score;
    }
    const complianceScore = Math.round(scoreSum / extractionDocs.length);

    // Register with / query the collusion graph. If identifying attributes
    // weren't provided in this call, we still query for any prior flags
    // rather than skipping collusion entirely.
    let collusionFlag = { bidder_id: bidderId, tender_id: tenderId, flagged: false, cluster_id: null, shared_with: [] };
    if (director_name && address && phone && bank_account) {
      await fetch(`${COLLUSION_URL}/bidders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bidder_id: bidderId, tender_id: tenderId, director_name, address, phone, bank_account }),
      });
    }
    const collusionResp = await fetch(`${COLLUSION_URL}/collusion/${encodeURIComponent(bidderId)}?tender_id=${encodeURIComponent(tenderId)}`);
    if (collusionResp.ok) {
      collusionFlag = await collusionResp.json();
    }

    const finalScore = {
      bidder_id: bidderId,
      tender_id: tenderId,
      compliance_score: complianceScore,
      risk_level: riskLevelFor(complianceScore),
      verification_breakdown: allChecks,
      collusion_flag: collusionFlag,
      ai_recommendation: collusionFlag.flagged
        ? `Compliance score ${complianceScore}/100. This bidder shares identifying details with another bidder on this tender (${collusionFlag.shared_with.map(s => s.shared_attribute).join(", ")}) -- review the collusion graph before qualifying.`
        : `Compliance score ${complianceScore}/100, no collusion signal detected. Review the evidence trail for any UNVERIFIED or FAIL checks before deciding.`,
      timestamp: new Date().toISOString(),
    };

    await Score.findOneAndUpdate({ bidder_id: bidderId, tender_id: tenderId }, finalScore, { upsert: true, new: true });

    res.json(finalScore);
  } catch (err) {
    res.status(500).json({ error: "orchestration failure", details: String(err) });
  }
});

// --- Reads ---------------------------------------------------------------

app.get("/bidders/:bidderId", async (req, res) => {
  const { bidderId } = req.params;
  const { tender_id: tenderId } = req.query;
  const query = tenderId ? { bidder_id: bidderId, tender_id: tenderId } : { bidder_id: bidderId };
  const score = await Score.findOne(query).sort({ createdAt: -1 });
  const extractions = await Extraction.find({ bidder_id: bidderId });
  if (!score) return res.status(404).json({ error: "no score found for this bidder -- call /verify first" });
  res.json({ score, extractions });
});

app.get("/tenders/:tenderId/bidders", async (req, res) => {
  const { tenderId } = req.params;
  const scores = await Score.find({ tender_id: tenderId }).sort({ compliance_score: 1 });
  res.json(scores);
});

// --- Decision + hash-chained audit log ------------------------------------

app.post("/bidders/:bidderId/decision", async (req, res) => {
  const { bidderId } = req.params;
  const { officer_id: officerId, decision, tender_id: tenderId } = req.body || {};
  if (!officerId || !decision || !tenderId) {
    return res.status(400).json({ error: "officer_id, decision, and tender_id are all required" });
  }
  if (!["QUALIFY", "DISQUALIFY"].includes(decision)) {
    return res.status(400).json({ error: "decision must be QUALIFY or DISQUALIFY" });
  }

  const score = await Score.findOne({ bidder_id: bidderId, tender_id: tenderId }).sort({ createdAt: -1 });
  if (!score) return res.status(404).json({ error: "no score found for this bidder -- call /verify first" });

  const lastEntry = await AuditLog.findOne({}).sort({ createdAt: -1 });
  const prevHash = lastEntry ? lastEntry.hash : "genesis";

  const entryId = crypto.randomUUID();
  const timestamp = new Date().toISOString();
  const scoreSnapshot = score.toObject();

  const canonicalBody = JSON.stringify({ entryId, bidderId, tenderId, officerId, decision, scoreSnapshot, timestamp });
  const hash = sha256(prevHash + canonicalBody);

  const entry = await AuditLog.create({
    entry_id: entryId,
    prev_hash: prevHash,
    hash,
    bidder_id: bidderId,
    tender_id: tenderId,
    officer_id: officerId,
    decision,
    score_snapshot: scoreSnapshot,
    timestamp,
  });

  res.json(entry);
});

app.get("/audit/:bidderId", async (req, res) => {
  const entries = await AuditLog.find({ bidder_id: req.params.bidderId }).sort({ createdAt: 1 });
  res.json(entries);
});

app.get("/health", async (req, res) => {
  res.json({ status: "ok", mongoConnected: mongoose.connection.readyState === 1, time: new Date().toISOString() });
});

async function start() {
  try {
    await mongoose.connect(MONGODB_URI, { serverSelectionTimeoutMS: 4000 });
    console.log("MongoDB connected");
  } catch (err) {
    console.error("MongoDB NOT connected -- start MongoDB and set MONGODB_URI. Server will still boot so you can check /health, but every route needing the DB will fail until it's connected.", err.message);
  }
  app.listen(PORT, () => console.log(`Backend listening on :${PORT}`));
}

start();
