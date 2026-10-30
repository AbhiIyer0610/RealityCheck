from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import JobStatus
from app.reasoning.models import Claim, Finding


class ComparisonDocument(BaseModel):
    job_id: UUID
    filename: str
    status: JobStatus
    analysis_provider: str

    model_config = ConfigDict(frozen=True)


class EvidenceSourceReference(BaseModel):
    evidence_id: UUID
    source_name: str
    source_id: str
    preview: str

    model_config = ConfigDict(frozen=True)


class ComparisonResponse(BaseModel):
    comparison_id: UUID
    created_at: datetime
    analysis_provider: str
    mode: str
    documents: list[ComparisonDocument] = Field(min_length=2, max_length=10)
    claims: list[Claim]
    findings: list[Finding]
    evidence_sources: list[EvidenceSourceReference]

    model_config = ConfigDict(frozen=True)
