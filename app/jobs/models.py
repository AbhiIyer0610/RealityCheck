from uuid import UUID
from enum import Enum
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.evidence.models import EvidenceObject
from app.ingestion.models import ExtractionResult
from app.reasoning.models import AnalysisStatus, Claim, Finding


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED}


class StoredJob(BaseModel):
    """Internal persisted job record. artifact_path is never returned by the API."""

    job_id: UUID
    artifact_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    status: JobStatus = JobStatus.PENDING
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_path: Path
    extraction_result: ExtractionResult | None = None
    evidence: list[EvidenceObject] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    analysis_status: AnalysisStatus = AnalysisStatus.NOT_CONFIGURED
    analysis_provider: str = "disabled"
    analysis_error_message: str | None = None
    processing_stage: str = "queued"
    progress_message: str = "Artifact accepted and waiting for a worker."
    error_message: str | None = None

    model_config = ConfigDict(frozen=True)
