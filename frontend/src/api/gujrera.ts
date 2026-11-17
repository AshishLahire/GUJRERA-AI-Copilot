import { API_BASE } from "./client";

export type TrustVerdict =
  | "verified"
  | "registered_with_warnings"
  | "mismatch"
  | "not_found"
  | "lapsed_or_revoked"
  | "no_rera_number"
  | "unreadable";

export type Lang = "en" | "gu" | "hi";

export interface RecordSource {
  type: string;
  id: string;
  is_mock: boolean;
}

export interface TrustCheck {
  id: string;
  status: "pass" | "fail" | "warn" | "info";
  severity: "critical" | "warning" | "info";
  title: string;
  detail: string;
  evidence: string | null;
  source: RecordSource | null;
  verdict_hint: string | null;
}

export interface TrustReport {
  verdict: TrustVerdict;
  headline: Record<Lang, string>;
  next_steps: string;
  checks: TrustCheck[];
  claim: {
    project_numbers: string[];
    agent_numbers: string[];
    possession: { value: string; text: string } | null;
    booking_percent: { value: number; text: string } | null;
    price: { value: number; text: string } | null;
  };
  // Registry rows (project, promoter scorecard, agent); fields vary by source.type
  records: Array<Record<string, unknown> & { source: RecordSource }>;
  is_mock: boolean;
  as_of: string | null;
  ocr?: {
    text: string;
    engine: string;
    valid: boolean;
    note: string | null;
    confidence?: number | null;
    low_confidence?: boolean;
  };
}

export interface TrustSample {
  id: string;
  kind: string;
  lang: Lang;
  label: string;
  text: string;
  expected: string[];
}

export interface ChatSource extends RecordSource {
  n: number;
}

export interface ChatOption {
  n: number;
  kind: string;
  id: number | string;
  label: string;
}

export interface ChatReply {
  session_id: string;
  lang: Lang;
  intent: string;
  text: string;
  sentences: { text: string; refs: number[] }[];
  sources: ChatSource[];
  cards: Array<Record<string, unknown> & { type: string }>;
  options: ChatOption[];
  suggestions: string[];
  is_mock: boolean;
  phrased_by: "template" | "llm";
  /** The same answer in English, from the same records, when the reply is in Gujarati or Hindi. */
  english?: string | null;
}

async function parse<T>(res: Response): Promise<T> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    // non-JSON body
  }
  if (!res.ok) {
    const body = payload as { detail?: string; error?: string } | null;
    throw new Error(body?.detail || body?.error || `Request failed with status ${res.status}`);
  }
  return payload as T;
}

export async function fetchTrustSamples(): Promise<{ items: TrustSample[] }> {
  return parse(await fetch(`${API_BASE}/api/gujrera/trust/samples`));
}

export async function checkTrustText(text: string): Promise<TrustReport> {
  return parse(
    await fetch(`${API_BASE}/api/gujrera/trust/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    })
  );
}

export async function checkTrustUpload(file: File): Promise<TrustReport> {
  const form = new FormData();
  form.append("file", file);
  return parse(await fetch(`${API_BASE}/api/gujrera/trust/upload`, { method: "POST", body: form }));
}

export interface AuthUser {
  username: string;
  role: "citizen" | "developer" | "agent" | "officer";
  display_name: string | null;
  organisation: string | null;
  district_scope: string | null;
  preferred_lang: Lang;
  is_demo: boolean;
}

export class AuthExpiredError extends Error {}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function sendChat(
  message: string,
  sessionId: string | null,
  lang: Lang | null,
  token: string | null = null
): Promise<ChatReply> {
  const res = await fetch(`${API_BASE}/api/gujrera/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ message, session_id: sessionId, lang }),
  });
  if (res.status === 401 && token) throw new AuthExpiredError("Your session has expired. Please log in again.");
  return parse(res);
}

export async function login(username: string, password: string): Promise<{ token: string; user: AuthUser }> {
  return parse(
    await fetch(`${API_BASE}/api/gujrera/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    })
  );
}

export async function fetchMe(token: string): Promise<{ user: AuthUser }> {
  const res = await fetch(`${API_BASE}/api/gujrera/auth/me`, { headers: authHeaders(token) });
  if (res.status === 401) throw new AuthExpiredError("Session expired");
  return parse(res);
}

export async function fetchChatStarters(): Promise<{ items: { lang: Lang; text: string }[] }> {
  return parse(await fetch(`${API_BASE}/api/gujrera/chat/starters`));
}

export interface Overview {
  projects: number;
  projects_by_status: Record<string, number>;
  ongoing_delayed: number;
  promoters: number;
  agents_active: number;
  complaints: number;
  complaints_open: number;
  complaints_by_status: Record<string, number>;
  projects_by_district: { district: string; count: number }[];
  is_mock: boolean;
}

export async function fetchOverview(): Promise<Overview> {
  return parse(await fetch(`${API_BASE}/api/gujrera/overview`));
}

export interface VoiceResult {
  text: string;
  language: string | null;
  duration_sec: number | null;
  low_quality: boolean;
  notes: string[];
}

export async function transcribeVoice(audio: Blob, lang: Lang | null): Promise<VoiceResult> {
  const form = new FormData();
  const ext = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("file", audio, `voice.${ext}`);
  if (lang) form.append("lang", lang);
  return parse(await fetch(`${API_BASE}/api/gujrera/voice/transcribe`, { method: "POST", body: form }));
}

export interface SelfServiceSummary {
  sentences: { text: string; citations: RecordSource[] }[];
  card: Record<string, unknown> & { role: "developer" | "agent" };
  is_mock: boolean;
}

export async function fetchSelfServiceSummary(token: string, lang: Lang): Promise<SelfServiceSummary> {
  const res = await fetch(`${API_BASE}/api/gujrera/self-service/summary?lang=${lang}`, {
    headers: authHeaders(token),
  });
  if (res.status === 401) throw new AuthExpiredError("Your session has expired. Please log in again.");
  return parse(res);
}

export interface AnalyticsResponse {
  intent: string;
  sentences: { text: string }[];
  card: (Record<string, unknown> & { type: "analytics" }) | null;
  suggestions: string[];
}

export async function runAnalytics(token: string, question: string, lang: Lang): Promise<AnalyticsResponse> {
  const res = await fetch(`${API_BASE}/api/gujrera/analytics/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ question, lang }),
  });
  if (res.status === 401) throw new AuthExpiredError("Your session has expired. Please log in again.");
  return parse(res);
}


// ------------------------------------------------------------ interest calculator
export interface CalcProject {
  id: number;
  name: string;
  name_gu: string | null;
  rera_no: string;
  district: string;
  status: string;
  promised: string;
}

export interface CalcRate {
  mclr: number;
  mclr_as_of: string;
  rate: number;
}

export interface CalcResult {
  project: { id: number; name: string; name_gu: string | null; rera_no: string; status: string; registered_promised: string };
  result: {
    mode: "stay" | "withdraw";
    rate_pct: number;
    rate_source: "agreement" | "sbi_mclr";
    promised: string;
    until: string;
    delay_days: number;
    principal: number;
    interest: number;
    total: number;
    refund_due_by: string | null;
    rows: { amount: number; from: string; to: string; days: number; interest: number }[];
  };
  sentences: { text: string; citations: { type: string; id: string }[] }[];
  is_mock: boolean;
}

export interface CalcRequest {
  project_id: number;
  mode: "stay" | "withdraw";
  payments: { amount: number; paid_on: string | null }[];
  possession_on?: string | null;
  promised_on?: string | null;
  rate?: number | null;
  lang: Lang;
}

export async function searchCalcProjects(q: string): Promise<{ items: CalcProject[] }> {
  return parse(await fetch(`${API_BASE}/api/gujrera/calc/projects?q=${encodeURIComponent(q)}`));
}

export async function fetchCalcRate(): Promise<CalcRate> {
  return parse(await fetch(`${API_BASE}/api/gujrera/calc/rate`));
}

export async function calculateInterest(body: CalcRequest): Promise<CalcResult> {
  return parse(
    await fetch(`${API_BASE}/api/gujrera/calc/interest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

/** Ask the shell to open the calculator, optionally prefilled (used by chat cards). */
export interface CalcSeed {
  projectId: number;
  projectName: string;
  mode: "stay" | "withdraw";
  amount: number | null;
}
export const OPEN_CALC_EVENT = "saathi:open-calculator";
export function openCalculator(seed: CalcSeed): void {
  window.dispatchEvent(new CustomEvent<CalcSeed>(OPEN_CALC_EVENT, { detail: seed }));
}


// ------------------------------------------------------------ risk watch (officers)
export interface RiskSignal {
  code: string;
  points: number;
  text: string;
  citations: { type: string; id: string }[];
}
export interface RiskItem {
  project_id: number;
  name: string;
  name_gu: string | null;
  rera_no: string;
  district: string;
  promoter: string;
  target: string;
  percent_complete: number | null;
  expected_percent: number | null;
  projected_finish: string | null;
  score: number;
  band: "high" | "medium" | "low";
  signals: RiskSignal[];
}
export interface RiskSummary {
  projects: number;
  by_band: { high: number; medium: number; low: number };
  by_signal: Record<string, number>;
  by_district: { district: string; high: number; medium: number; low: number }[];
}
export interface RiskResponse {
  summary: RiskSummary;
  items: RiskItem[];
  district_scope: string | null;
}

export async function fetchRisk(token: string, lang: Lang, district: string | null): Promise<RiskResponse> {
  const qs = new URLSearchParams({ lang, ...(district ? { district } : {}) });
  const res = await fetch(`${API_BASE}/api/gujrera/risk/projects?${qs}`, { headers: authHeaders(token) });
  if (res.status === 401) throw new AuthExpiredError("Your session has expired. Please log in again.");
  return parse(res);
}

/** Ask the shell to switch page (used by chat cards). */
export const NAVIGATE_EVENT = "saathi:navigate";
export function navigateTo(page: string): void {
  window.dispatchEvent(new CustomEvent<string>(NAVIGATE_EVENT, { detail: page }));
}


// ------------------------------------------------------------ ad reports and enforcement
export interface AdReportReceipt {
  received: boolean;
  receipt: string;
  duplicate: boolean;
  kind: string;
  message: string;
}

export async function reportAd(text: string, channel: "text" | "upload" | "chat", token: string | null): Promise<AdReportReceipt> {
  return parse(
    await fetch(`${API_BASE}/api/gujrera/trust/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify({ text, channel }),
    }),
  );
}

export interface EnfCase {
  id: number;
  ref_no: string;
  kind: "unregistered" | "lapsed" | "misleading";
  law: string;
  title: string;
  advertised_promoter: string | null;
  district: string | null;
  claimed_rera: string | null;
  project_id: number | null;
  status: "new" | "reviewing" | "notice_issued" | "closed";
  outcome: string | null;
  opened_on: string;
  updated_on: string;
  reports: number;
  last_reported: string;
  phones: string[];
  websites: string[];
  asks_payment_to_account: boolean;
  notes?: string | null;
  evidence?: {
    id: number;
    reported_on: string;
    channel: string;
    verdict: string;
    claimed_rera: string | null;
    advertised_project: string | null;
    advertised_promoter: string | null;
    problems: string[];
    excerpt: string;
  }[];
}

export interface EnfList {
  counts: { open: number; new: number; reports: number; by_kind: Record<string, number> };
  items: EnfCase[];
  district_scope: string | null;
}

async function officerFetch<T>(url: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...init, headers: { ...(init?.headers ?? {}), ...authHeaders(token) } });
  if (res.status === 401) throw new AuthExpiredError("Your session has expired. Please log in again.");
  return parse(res);
}

export function fetchCases(token: string, filters: { status?: string; kind?: string; district?: string }): Promise<EnfList> {
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v) as [string, string][]);
  return officerFetch(`${API_BASE}/api/gujrera/enforcement/cases?${qs}`, token);
}

export function fetchCase(token: string, id: number): Promise<EnfCase> {
  return officerFetch(`${API_BASE}/api/gujrera/enforcement/cases/${id}`, token);
}

export function updateCase(token: string, id: number, body: { status?: string; outcome?: string; note?: string }): Promise<EnfCase> {
  return officerFetch(`${API_BASE}/api/gujrera/enforcement/cases/${id}`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
