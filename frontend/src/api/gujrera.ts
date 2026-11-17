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
