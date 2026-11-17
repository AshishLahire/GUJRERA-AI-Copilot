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
  ocr?: { text: string; engine: string; valid: boolean; note: string | null };
}

export interface TrustSample {
  id: string;
  kind: string;
  lang: Lang;
  label: string;
  text: string;
  expected: string[];
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
