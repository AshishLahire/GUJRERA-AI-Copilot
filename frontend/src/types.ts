export const PRODUCT_NAME = "Pramaan";
export const PRODUCT_SUBTITLE =
  "Document & claim verification for Indian languages";

const ACRONYMS = new Set(["I4C", "OMC", "RBI", "CBSE", "MNRE", "MORTH", "SCI", "PIB"]);

export function formatNarrativeLabel(
  narrative: string | null | undefined,
  fallback?: string | null
): string {
  if (!narrative) {
    return fallback || "Document sample";
  }
  const stripped = narrative.replace(/^NAR[-_]/i, "");
  const words = stripped.split(/[-_]+/).filter(Boolean);
  if (words.length === 0) return fallback || narrative;
  return words
    .map((w, idx) => {
      const upper = w.toUpperCase();
      if (ACRONYMS.has(upper)) return upper;
      const low = w.toLowerCase();
      return idx === 0 ? low.charAt(0).toUpperCase() + low.slice(1) : low;
    })
    .join(" ");
}

export type SampleGroup = "fake" | "genuine" | "synthetic";

export interface HealthResponse {
  status: string;
  offline_mode: boolean;
  local_llm_model?: string;
  ollama_enabled: boolean;
  ollama_reachable?: boolean;
  vlm_model: string;
  gemini_configured: boolean;
  gemini_model: string;
  daily_api_calls_used: number;
  daily_api_call_limit: number;
  speech_model_loaded?: boolean;
}

export interface SampleItem {
  id: string;
  demo_order?: number | null;
  talking_point?: string | null;
  group: SampleGroup;
  label: string;
  language: string;
  narrative: string | null;
  note: string | null;
  expected_issuer: string | null;
  expected_issuer_id: string | null;
  expected_reference_no: string | null;
  thumbnail_url: string;
  filename: string;
  width: number;
  height: number;
}

export interface SamplesListResponse {
  count: number;
  items: SampleItem[];
}

export interface ExtractedFields {
  reference_numbers: string[];
  near_duplicate_references?: string[][];
  dates: string[];
  phone_numbers: string[];
  emails: string[];
  upi_ids?: string[];
  urls: string[];
  suspicious_domains?: string[];
  rupee_amounts: string[];
  subject: string | null;
}

export interface DetectedIssuer {
  issuer_id: string;
  name: string;
}

export type FindingSeverity = "info" | "warning" | "critical";
export type RiskLevel = "low" | "medium" | "high";

export interface ForensicFinding {
  cue_id: string;
  severity: FindingSeverity;
  points: number;
  title: string;
  explanation: string;
  evidence: string;
  char_start: number;
  char_end: number;
  rule_status: "verified" | "unverified";
}

export interface OverlayLineSpan {
  char_start: number;
  char_end: number;
}

export interface ForensicResult {
  risk_level: RiskLevel;
  risk_score: number;
  detected_issuer: DetectedIssuer | null;
  findings: ForensicFinding[];
  overlay_filtered_count?: number;
  overlay_line_spans?: OverlayLineSpan[];
  transcript_transliterated?: boolean;
  transliteration_note?: string | null;
}

export interface VisualRegion {
  kind: "seal" | "signature" | "emblem" | "edit_trace";
  box: [number, number, number, number];
  confidence: number;
  note: string;
}

export interface VisualForensicResult {
  analysed: boolean;
  regions: VisualRegion[];
  findings: ForensicFinding[];
  editing_software: string | null;
  has_seal: boolean;
  has_signature: boolean;
  has_emblem: boolean;
  note: string | null;
}

export type TestLabel = "real" | "fake" | "synthetic_clean" | "synthetic_forged";

export interface TestItem {
  id: string;
  label: TestLabel;
  title: string | null;
  claimed_issuer_id: string | null;
  language: string | null;
  in_official_index: boolean | null;
  in_index?: boolean | null;
  cleaning: string | null;
  variant_of: string | null;
  note: string | null;
  has_original: boolean;
  thumbnail_url: string;
}

export type ClaimType =
  | "forged_document"
  | "rumour"
  | "official_notice"
  | "other";

export interface ClaimResult {
  canonical_claim_en: string | null;
  claim_language: string;
  claimed_issuer: string | null;
  claimed_issuer_id?: string | null;
  action: string | null;
  effective_date: string | null;
  effective_date_raw?: string | null;
  amounts: string[];
  audience: string | null;
  claim_type: ClaimType;
  confidence: number;
  from_cache: boolean;
  status_note?: string | null;
  error?: string | null;
}

export type MatchLabel = "strong" | "possible" | "none" | "related";

export interface MatchItem {
  doc_id: string;
  collection: "debunks" | "official";
  title: string;
  snippet: string;
  date: string | null;
  url: string | null;
  reference_no?: string | null;
  narrative_id?: string | null;
  narrative_status?: "annotated" | "approximate" | null;
  official_fact?: string | null;
  score: number;
  rrf_score: number;
  cosine_score: number | null;
  bm25_score: number;
  label: MatchLabel;
  confidence_label?: string;
  relation_note?: string | null;
  exact_reference_match: boolean;
  downgraded_from_overlay_overlap?: boolean;
  downgrade_note?: string | null;
}

export interface RetrievalResult {
  debunks: MatchItem[];
  official: MatchItem[];
  retrieval_mode: "hybrid" | "bm25_only";
  mode_note?: string | null;
  queries_used: string[];
  ground_truth?: GroundTruthResult | null;
}

export interface GroundTruthMatch {
  record_id: string;
  verdict: "debunked" | "official";
  kind: string;
  score: number;
  claim: string;
  official_fact: string | null;
  issuer_id: string | null;
  reference_no: string | null;
  reference_link: string | null;
  source: string | null;
  date: string | null;
  narrative_id: string | null;
}

export interface GroundTruthResult {
  status: "debunked" | "official" | "no_record" | "skipped";
  similarity: number;
  best: GroundTruthMatch | null;
  top_matches: GroundTruthMatch[];
  note: string | null;
  database_size: number;
}

export interface EvidenceLink {
  title: string;
  url: string | null;
  collection: "debunks" | "official";
  doc_id: string;
  label: string;
}

export type VerdictColor = "red" | "green" | "amber" | "grey";

export interface VerdictResult {
  verdict_key:
    | "debunked"
    | "matches_official"
    | "altered_official_copy"
    | "likely_forged"
    | "suspicious_unverified"
    | "unverified";
  color: VerdictColor;
  title: string;
  reason: string;
  evidence_links: EvidenceLink[];
  overlay_downgrade_note?: string | null;
  official_clarification?: string | null;
  decided_by?: "source_match" | "ground_truth" | "forensics" | "none";
}

export interface OCRResult {
  image_hash: string;
  final_text: string;
  engine_used: string;
  valid: boolean;
  fields: ExtractedFields;
  from_cache: boolean;
  markdown_stripped: boolean;
  time_ms: number;
  note?: string | null;
  error: string | null;
  cache_source?: string | null;
  older_ocr_settings?: boolean;
  script?: string | null;
  language_confidence?: number | null;
  language_name?: string | null;
  text_direction?: "ltr" | "rtl";
  primary_language?: string | null;
  languages_present?: Array<{ language: string; share: number; language_name: string; script: string }>;
  language_badge?: string | null;
  is_language_uncertain?: boolean;
  // Augmented fields returned by backend API
  sample_id?: string;
  simulate_unseen?: boolean;
  demo_order?: number | null;
  talking_point?: string | null;
  group?: SampleGroup;
  language?: string;
  narrative?: string | null;
  sample_note?: string | null;
  expected_issuer?: string | null;
  expected_issuer_id?: string | null;
  expected_reference_no?: string | null;
  filename?: string;
  width?: number;
  height?: number;
  image_url?: string;
  forensics?: ForensicResult;
  visual?: VisualForensicResult;
  claim?: ClaimResult;
  matches?: RetrievalResult;
  verdict?: VerdictResult;
  narrative_result?: NarrativeMatchResult;
  is_audio?: boolean;
  is_text?: boolean;
  test_item?: TestItem;
  audio_url?: string;
  job_id?: string;
  transcription?: AudioTranscriptionResult;
  transcript_transliterated?: boolean;
  transliteration_note?: string | null;
}

export interface AudioSegment {
  start: number;
  end: number;
  text: string;
}

export interface AudioCandidate {
  code: string;
  name: string;
  prob: number;
}

export interface AudioDetection {
  mode: "auto" | "manual";
  detected: string | null;
  confidence: number | null;
  candidates: AudioCandidate[];
  needs_confirmation: boolean;
  message?: string | null;
}

export interface AudioTranscriptionResult {
  text: string;
  segments: AudioSegment[];
  language: string;
  language_name: string;
  engine: string;
  detection: AudioDetection;
  duration_seconds: number;
  notes: string;
  weak_language_warning?: string | null;
  error?: boolean;
  transcript_transliterated?: boolean;
  transliteration_note?: string | null;
}

export interface LanguageOption {
  code: string;
  name: string;
  script: string;
}

export interface SharedIndicatorItem {
  indicator_id: string;
  kind: "phone" | "email" | "domain" | "reference" | "signatory";
  value: string;
  linked_records: string[];
  issuers: string[];
  years: string[];
  summary: string;
}

export interface NarrativeMatchResult {
  assigned: boolean;
  cluster_id: string | null;
  narrative_name: string | null;
  size: number;
  first_date: string | null;
  last_date: string | null;
  debunks_count: number;
  similarity: number;
  shared_indicators: SharedIndicatorItem[];
  summary_text: string | null;
}

export interface NarrativeExemplarPost {
  doc_id: string;
  title: string;
  url: string | null;
  date: string | null;
  snippet: string | null;
}

export interface MonthlyDebunkCount {
  month: string;
  count: number;
}

export interface NarrativeClusterSummary {
  id: string;
  name: string;
  size: number;
  claimed_issuers: { issuer: string; count: number }[];
  first_date: string | null;
  last_date: string | null;
  languages: string[];
  monthly_debunks: MonthlyDebunkCount[];
  exemplars: NarrativeExemplarPost[];
  shared_indicators_count: number;
  keyword_narrative_id?: string | null;
}

export interface NarrativeClusterDetail extends NarrativeClusterSummary {
  shared_indicators: SharedIndicatorItem[];
  skipped_undated_posts: number;
}
