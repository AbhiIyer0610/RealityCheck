from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClaimCategory(str, Enum):
    INTENT = "intent"
    REQUIREMENT = "requirement"
    IMPLEMENTATION = "implementation"
    CONFIGURATION = "configuration"
    OBSERVATION = "observation"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


class ClaimKind(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class AnalysisStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FindingStatus(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"
    REALITY_GAP = "reality_gap"


class Claim(BaseModel):
    claim_id: UUID = Field(default_factory=uuid4)
    text: str = Field(min_length=1, max_length=2000)
    category: ClaimCategory = ClaimCategory.UNKNOWN
    kind: ClaimKind = ClaimKind.EXPLICIT
    evidence_ids: list[UUID] = Field(min_length=1, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(frozen=True)


class Finding(BaseModel):
    finding_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=240)
    explanation: str = Field(min_length=1, max_length=3000)
    status: FindingStatus
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=30)
    claim_ids: list[UUID] = Field(default_factory=list, max_length=30)
    confidence: float = Field(ge=0.0, le=1.0)
    recommendation: str | None = Field(default=None, max_length=2000)
    impact: str | None = Field(default=None, max_length=1200)
    alternative_explanation: str | None = Field(default=None, max_length=1200)
    validation_test: str | None = Field(default=None, max_length=1200)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def must_have_traceable_basis(self) -> "Finding":
        if not self.evidence_ids and not self.claim_ids:
            raise ValueError("A finding must reference at least one evidence item or claim.")
        return self
