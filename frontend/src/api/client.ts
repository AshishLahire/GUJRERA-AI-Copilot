import {
  HealthResponse,
  NarrativeClusterDetail,
  NarrativeClusterSummary,
  OCRResult,
  LanguageOption,
  SamplesListResponse,
  TestItem,
} from "../types";

export const API_BASE = (
  import.meta.env.VITE_API_BASE ?? ""
).replace(/\/+$/, "");

export function resolveApiUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function parseResponse<T>(res: Response): Promise<T> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    // Non-JSON response
  }

  if (!res.ok) {
    if (res.status === 503) {
      throw new Error("Cloud OCR is busy, try again (Gemini busy, try again)");
    }
    const errObj = payload as { error?: string; detail?: string } | null;
    const msg =
      errObj?.error ||
      errObj?.detail ||
      `Request failed with status ${res.status}`;
    throw new Error(msg);
  }
  return payload as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/health`);
  return parseResponse<HealthResponse>(res);
}

export async function fetchSamples(): Promise<SamplesListResponse> {
  const res = await fetch(`${API_BASE}/api/samples`);
  return parseResponse<SamplesListResponse>(res);
}

export async function runSampleOcr(
  sampleId: string,
  allowFallback: boolean,
  simulateUnseen = false
): Promise<OCRResult> {
  const url = `${API_BASE}/api/ocr/sample/${encodeURIComponent(
    sampleId
  )}?allow_fallback=${allowFallback ? "true" : "false"}&simulate_unseen=${
    simulateUnseen ? "true" : "false"
  }`;
  const res = await fetch(url, { method: "POST" });
  return parseResponse<OCRResult>(res);
}

export async function runUploadOcr(
  file: File,
  allowFallback: boolean
): Promise<OCRResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("allow_fallback", allowFallback ? "true" : "false");

  const res = await fetch(`${API_BASE}/api/ocr/upload`, {
    method: "POST",
    body: formData,
  });
  return parseResponse<OCRResult>(res);
}

export async function checkText(
  text: string,
  allowFallback: boolean
): Promise<OCRResult> {
  const res = await fetch(`${API_BASE}/api/check/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, allow_fallback: allowFallback }),
  });
  return parseResponse<OCRResult>(res);
}

export async function fetchTestset(): Promise<{ count: number; items: TestItem[] }> {
  const res = await fetch(`${API_BASE}/api/testset`);
  return parseResponse<{ count: number; items: TestItem[] }>(res);
}

export async function runTestItem(
  itemId: string,
  allowFallback: boolean,
  unseen: boolean
): Promise<OCRResult> {
  const res = await fetch(
    `${API_BASE}/api/testset/${encodeURIComponent(itemId)}/run?allow_fallback=${
      allowFallback ? "true" : "false"
    }&simulate_unseen=${unseen ? "true" : "false"}`,
    { method: "POST" }
  );
  return parseResponse<OCRResult>(res);
}

export async function fetchNarratives(
  sort: "size" | "recent" = "size",
  search?: string,
  issuer?: string
): Promise<{ count: number; items: NarrativeClusterSummary[] }> {
  const params = new URLSearchParams();
  params.set("sort", sort);
  if (search) params.set("search", search);
  if (issuer) params.set("issuer", issuer);
  const res = await fetch(`${API_BASE}/api/narratives?${params.toString()}`);
  return parseResponse<{ count: number; items: NarrativeClusterSummary[] }>(res);
}

export async function fetchNarrativeDetail(
  clusterId: string
): Promise<NarrativeClusterDetail> {
  const res = await fetch(
    `${API_BASE}/api/narratives/${encodeURIComponent(clusterId)}`
  );
  return parseResponse<NarrativeClusterDetail>(res);
}

export async function fetchLanguages(): Promise<{ languages: LanguageOption[] }> {
  const res = await fetch(`${API_BASE}/api/languages`);
  return parseResponse<{ languages: LanguageOption[] }>(res);
}

export async function uploadAudio(
  file: File,
  language?: string,
  allowFallback = false
): Promise<OCRResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (language) {
    formData.append("language", language);
  }
  formData.append("allow_fallback", allowFallback ? "true" : "false");

  const res = await fetch(`${API_BASE}/api/transcribe/upload`, {
    method: "POST",
    body: formData,
  });
  return parseResponse<OCRResult>(res);
}

export async function retranscribeAudio(
  jobId: string,
  language: string,
  allowFallback = false
): Promise<OCRResult> {
  const formData = new FormData();
  formData.append("language", language);
  formData.append("allow_fallback", allowFallback ? "true" : "false");

  const res = await fetch(`${API_BASE}/api/transcribe/${encodeURIComponent(jobId)}/language`, {
    method: "POST",
    body: formData,
  });
  return parseResponse<OCRResult>(res);
}
