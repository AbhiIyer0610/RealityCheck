export type JobStatus = "pending" | "running" | "succeeded" | "partial" | "failed";
export type ExtractionStatus = "success" | "partial" | "failed";

export interface EvidenceLocation {
  page?: number | null;
  line_start?: number | null;
  line_end?: number | null;
  character_start?: number | null;
  character_end?: number | null;
  record_id?: string | null;
  bounding_box?: { x1: number; y1: number; x2: number; y2: number } | null;
}

export interface EvidenceObject {
  evidence_id: string;
  evidence_type: string;
  content?: string | null;
  structured_content?: Record<string, unknown> | null;
  confidence?: number | null;
  provenance: {
    source_id: string;
    source_name: string;
    artifact_type: string;
    location?: EvidenceLocation | null;
    extraction_method: string;
    extractor_version?: string | null;
  };
  extracted_at: string;
  metadata: Record<string, unknown>;
}

export interface ExtractionDiagnostic {
  message: string;
  severity: string;
  location?: EvidenceLocation | null;
  metadata: Record<string, unknown>;
}

export interface JobResponse {
  job_id: string;
  artifact_id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  extraction_status?: ExtractionStatus | null;
  element_count: number;
  evidence_count: number;
  diagnostics: ExtractionDiagnostic[];
  error_message?: string | null;
  processing_stage: string;
  progress_message: string;
  analysis_status: AnalysisStatus;
  analysis_provider: "disabled" | "nebius" | "offline_demo" | string;
  analysis_error_message?: string | null;
  claim_count: number;
  finding_count: number;
}

export interface EvidenceListResponse {
  job_id: string;
  status: JobStatus;
  count: number;
  items: EvidenceObject[];
}


export type AnalysisStatus = "not_configured" | "pending" | "running" | "succeeded" | "failed";
export type FindingStatus = "verified" | "inferred" | "uncertain" | "reality_gap";

export interface Claim {
  claim_id: string;
  text: string;
  category: string;
  kind: "explicit" | "inferred";
  evidence_ids: string[];
  confidence: number;
}

export interface Finding {
  finding_id: string;
  title: string;
  explanation: string;
  status: FindingStatus;
  evidence_ids: string[];
  claim_ids: string[];
  confidence: number;
  recommendation?: string | null;
  impact?: string | null;
  alternative_explanation?: string | null;
  validation_test?: string | null;
}

export interface AnalysisResponse {
  job_id: string;
  status: JobStatus;
  analysis_status: AnalysisStatus;
  analysis_provider: "disabled" | "nebius" | "offline_demo" | string;
  processing_stage: string;
  progress_message: string;
  error_message?: string | null;
  claims: Claim[];
  findings: Finding[];
}

export interface ComparisonDocument {
  job_id: string;
  filename: string;
  status: JobStatus;
  analysis_provider: string;
}

export interface EvidenceSourceReference {
  evidence_id: string;
  source_name: string;
  source_id: string;
  preview: string;
}

export interface ComparisonResponse {
  comparison_id: string;
  created_at: string;
  analysis_provider: string;
  mode: "offline_heuristic" | "model_reconciliation" | string;
  documents: ComparisonDocument[];
  claims: Claim[];
  findings: Finding[];
  evidence_sources: EvidenceSourceReference[];
}

export interface HistoryItem {
  id: string;
  kind: "document" | "comparison";
  title: string;
  created_at: string;
  status: string;
  document_count: number;
  claim_count: number;
  finding_count: number;
  document_names: string[];
  job_id?: string | null;
  comparison_id?: string | null;
  source_job_ids?: string[];
}

export interface HistoryResponse {
  items: HistoryItem[];
  total: number;
}


export interface TavilySearchResult {
  title: string;
  url: string;
  content: string;
  score?: number | null;
}

export interface TavilySearchResponse {
  query: string;
  results: TavilySearchResult[];
  source: string;
  note: string;
}
