from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field

from app.core.provenance import EvidenceLocation


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ExtractedElementType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    STRUCTURED_DATA = "structured_data"
    UNKNOWN = "unknown"


class ExtractionDiagnostic(BaseModel):
    message: str = Field(min_length=1)
    severity: str = Field(min_length=1)

    location: EvidenceLocation | None = None

    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ExtractedElement(BaseModel):
    element_id: UUID = Field(default_factory=uuid4)

    element_type: ExtractedElementType

    content: str | None = None

    structured_content: dict[str, object] | None = None

    location: EvidenceLocation | None = None

    extraction_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ExtractionResult(BaseModel):
    artifact_id: UUID

    status: ExtractionStatus

    elements: list[ExtractedElement] = Field(default_factory=list)

    diagnostics: list[ExtractionDiagnostic] = Field(
        default_factory=list
    )

    extractor_name: str = Field(min_length=1)

    extractor_version: str | None = None

    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ArtifactStatus(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Artifact(BaseModel):
    """
    Represents a user-provided source artifact.
    An Artifact is the original input to the ingestion pipeline. It is not evidence itself.
    """

    artifact_id: UUID = Field(default_factory=uuid4)

    filename: str = Field(min_length=1)

    media_type: str = Field(min_length=1)

    size_bytes: int = Field(ge=0)

    status: ArtifactStatus = ArtifactStatus.RECEIVED

    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)