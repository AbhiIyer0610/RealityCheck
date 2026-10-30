from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.provenance import EvidenceLocation


class EvidenceType(str, Enum):
    INTENT = "intent"
    REQUIREMENT = "requirement"
    IMPLEMENTATION = "implementation"
    CONFIGURATION = "configuration"
    OBSERVATION = "observation"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


class ArtifactType(str, Enum):
    TEXT = "text"
    PDF = "pdf"
    IMAGE = "image"
    CODE = "code"
    JSON = "json"
    YAML = "yaml"
    TABLE = "table"
    EVENT = "event"
    UNKNOWN = "unknown"


class EvidenceProvenance(BaseModel):
    """
    Information describing where the evidence came from and how it was extracted.
    """

    source_id: str
    source_name: str
    artifact_type: ArtifactType

    location: EvidenceLocation | None = None

    extraction_method: str
    extractor_version: str | None = None

    model_config = ConfigDict(frozen=True)


class EvidenceObject(BaseModel):
    """
    Canonical representation of a piece of evidence.
    Evidence is not necessarily a claim. It is an auditable piece of information
    extracted from an artifact.
    """

    evidence_id: UUID = Field(default_factory=uuid4)

    evidence_type: EvidenceType

    content: str | None = Field(default=None, min_length=1)
    structured_content: dict[str, object] | None = None

    confidence: float | None = Field(
        ge=0.0,
        le=1.0,
    )

    provenance: EvidenceProvenance

    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_evidence_content(self) -> "EvidenceObject":
        has_text = self.content is not None and bool(self.content.strip())
        has_structured_content = bool(self.structured_content)

        if not has_text and not has_structured_content:
            raise ValueError(
                "Evidence must contain non-empty text or structured content."
            )

        return self