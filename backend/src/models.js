import mongoose from "mongoose";

const { Schema } = mongoose;

// Mirrors extraction_output.schema.json
const ExtractionSchema = new Schema(
  {
    bidder_id: { type: String, required: true, index: true },
    document_type: { type: String, enum: ["PAN", "GST", "UDYAM", "EPFO"], required: true },
    extracted_fields: { type: Object, required: true },
    confidence: { type: Object, default: {} },
    raw_ocr_text: { type: String, default: "" },
    source_s3_key: { type: String, default: "" },
  },
  { timestamps: true }
);

// Mirrors final_score.schema.json
const ScoreSchema = new Schema(
  {
    bidder_id: { type: String, required: true, index: true },
    tender_id: { type: String, required: true, index: true },
    compliance_score: { type: Number, required: true },
    risk_level: { type: String, enum: ["LOW", "MEDIUM", "HIGH"], required: true },
    verification_breakdown: { type: Array, default: [] },
    collusion_flag: { type: Object, default: {} },
    ai_recommendation: { type: String, default: "" },
    timestamp: { type: String, required: true },
  },
  { timestamps: true }
);

// Mirrors audit_log_entry.schema.json -- insert-only, enforced at the route
// level (no update/delete routes exist for this collection at all).
const AuditLogSchema = new Schema(
  {
    entry_id: { type: String, required: true, unique: true },
    prev_hash: { type: String, required: true },
    hash: { type: String, required: true },
    bidder_id: { type: String, required: true, index: true },
    tender_id: { type: String, required: true },
    officer_id: { type: String, required: true },
    decision: { type: String, enum: ["QUALIFY", "DISQUALIFY"], required: true },
    score_snapshot: { type: Object, required: true },
    timestamp: { type: String, required: true },
  },
  { timestamps: true }
);

export const Extraction = mongoose.model("Extraction", ExtractionSchema);
export const Score = mongoose.model("Score", ScoreSchema);
export const AuditLog = mongoose.model("AuditLog", AuditLogSchema);
