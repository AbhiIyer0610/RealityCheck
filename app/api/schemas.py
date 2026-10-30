from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evidence.models import EvidenceObject
from app.jobs.models import JobStatus, StoredJob
from app.ingestion.models import ExtractionDiagnostic, ExtractionStatus
from app.reasoning.models import AnalysisStatus, Claim, Finding
from app.reasoning.comparison import ComparisonResponse


class JobResponse(BaseModel):
    job_id: UUID
    artifact_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    extraction_status: ExtractionStatus | None
    element_count: int
    evidence_count: int
    diagnostics: list[ExtractionDiagnostic]
    error_message: str | None
    processing_stage: str
    progress_message: str
    analysis_status: AnalysisStatus
    analysis_provider: str
    analysis_error_message: str | None
    claim_count: int
    finding_count: int

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_stored_job(cls, job: StoredJob) -> "JobResponse":
        result = job.extraction_result
        return cls(
            job_id=job.job_id,
            artifact_id=job.artifact_id,
            filename=job.filename,
            media_type=job.media_type,
            size_bytes=job.size_bytes,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            extraction_status=result.status if result else None,
            element_count=len(result.elements) if result else 0,
            evidence_count=len(job.evidence),
            diagnostics=result.diagnostics if result else [],
            error_message=job.error_message,
            processing_stage=job.processing_stage,
            progress_message=job.progress_message,
            analysis_status=job.analysis_status,
            analysis_provider=job.analysis_provider,
            analysis_error_message=job.analysis_error_message,
            claim_count=len(job.claims),
            finding_count=len(job.findings),
        )


class AnalysisResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    analysis_status: AnalysisStatus
    analysis_provider: str
    processing_stage: str
    progress_message: str
    error_message: str | None
    claims: list[Claim]
    findings: list[Finding]


class EvidenceListResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    count: int
    items: list[EvidenceObject]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class CompareJobsRequest(BaseModel):
    job_ids: list[UUID] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def require_unique_job_ids(self) -> "CompareJobsRequest":
        if len(set(self.job_ids)) != len(self.job_ids):
            raise ValueError("Each job ID must be unique.")
        return self


class ComparisonApiResponse(ComparisonResponse):
    pass


class HistoryItem(BaseModel):
    id: UUID
    kind: Literal["document", "comparison"]
    title: str
    created_at: datetime
    status: str
    document_count: int
    claim_count: int
    finding_count: int
    document_names: list[str]
    job_id: UUID | None = None
    comparison_id: UUID | None = None
    # Source jobs are implementation records grouped under a saved comparison.
    source_job_ids: list[UUID] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    total: int


class TavilySearchRequest(BaseModel):
    query: str = Field(min_length=4, max_length=500, description="A public-information query. Do not submit confidential document text.")
    include_domains: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_query(self) -> "TavilySearchRequest":
        self.query = self.query.strip()
        if len(self.query) < 4:
            raise ValueError("Search query must contain at least four non-whitespace characters.")
        self.include_domains = [domain.strip().lower() for domain in self.include_domains if domain.strip()]
        return self


class TavilySearchResult(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None


class TavilySearchResponse(BaseModel):
    query: str
    results: list[TavilySearchResult]
    source: str = "Tavily Search"
    note: str = "External search results are untrusted references, not proof of internal runtime behavior."
