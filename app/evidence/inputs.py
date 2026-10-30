
from pydantic import BaseModel, Field, model_validator

from app.core.provenance import EvidenceLocation
from app.evidence.models import ArtifactType, EvidenceType


class EvidenceInput(BaseModel):
    """
    Normalized input supplied by an extractor to the EvidenceFactory.
    Supports both textual and structured evidence without depending on any particular extraction library.
    """

    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)

    artifact_type: ArtifactType

    content: str | None = Field(default=None, min_length=1)
    structured_content: dict[str, object] | None = None

    evidence_type: EvidenceType = EvidenceType.UNKNOWN

    confidence: float | None = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )

    location: EvidenceLocation | None = None

    extraction_method: str = Field(min_length=1)

    extractor_version: str | None = None

    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evidence_content(self) -> "EvidenceInput":
        has_text = self.content is not None and bool(self.content.strip())
        has_structured_content = bool(self.structured_content)

        if not has_text and not has_structured_content:
            raise ValueError(
                "Evidence must contain non-empty text or structured content."
            )

        return self
