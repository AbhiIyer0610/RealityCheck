import type { AnalysisResponse, EvidenceListResponse, JobResponse } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function readResponse<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload
      ? (payload as { detail?: unknown }).detail
      : null;
    const message = typeof detail === "string" ? detail : `Request failed with HTTP ${response.status}.`;
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export async function uploadArtifact(file: File, signal?: AbortSignal): Promise<JobResponse> {
  const body = new FormData();
  body.append("file", file);
  // Do not set Content-Type manually: fetch must add the multipart boundary.
  const response = await fetch(`${API_BASE_URL}/api/v1/artifacts`, {
    method: "POST",
    body,
    signal,
    headers: { Accept: "application/json" },
  });
  return readResponse<JobResponse>(response);
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<JobResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  return readResponse<JobResponse>(response);
}

export async function getEvidence(jobId: string, signal?: AbortSignal): Promise<EvidenceListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}/evidence`, {
    headers: { Accept: "application/json" },
    signal,
  });
  return readResponse<EvidenceListResponse>(response);
}

export { API_BASE_URL };


export async function getAnalysis(jobId: string, signal?: AbortSignal): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}/analysis`, {
    headers: { Accept: "application/json" },
    signal,
  });
  return readResponse<AnalysisResponse>(response);
}

export async function createComparison(jobIds: string[]): Promise<import("./types").ComparisonResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/comparisons`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ job_ids: jobIds }),
  });
  return readResponse<import("./types").ComparisonResponse>(response);
}

export async function getComparison(comparisonId: string): Promise<import("./types").ComparisonResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/comparisons/${encodeURIComponent(comparisonId)}`, {
    headers: { Accept: "application/json" },
  });
  return readResponse<import("./types").ComparisonResponse>(response);
}


export async function getHistory(): Promise<import("./types").HistoryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/history`, { headers: { Accept: "application/json" } });
  return readResponse<import("./types").HistoryResponse>(response);
}

export async function deleteHistoryItem(item: import("./types").HistoryItem): Promise<void> {
  const path = item.kind === "comparison"
    ? `/api/v1/comparisons/${encodeURIComponent(item.comparison_id || item.id)}`
    : `/api/v1/jobs/${encodeURIComponent(item.job_id || item.id)}/history`;
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "DELETE", headers: { Accept: "application/json" } });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = typeof payload === "object" && payload !== null && "detail" in payload
      ? (payload as { detail?: unknown }).detail : null;
    throw new ApiError(typeof detail === "string" ? detail : `Request failed with HTTP ${response.status}.`, response.status);
  }
}


export async function searchTavily(query: string, includeDomains: string[] = []): Promise<import("./types").TavilySearchResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/research/tavily/search`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ query, include_domains: includeDomains }),
  });
  return readResponse<import("./types").TavilySearchResponse>(response);
}
