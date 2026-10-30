from uuid import uuid4
from datetime import datetime, timezone

from app.evidence.inputs import EvidenceInput
from app.evidence.models import (
    EvidenceObject,
    EvidenceProvenance,
)


class EvidenceFactory:
    """
    Converts normalized extraction input into canonical EvidenceObjects.
    """

    @staticmethod
    def create(evidence_input: EvidenceInput) -> EvidenceObject:
        provenance = EvidenceProvenance(
            source_id=evidence_input.source_id,
            source_name=evidence_input.source_name,
            artifact_type=evidence_input.artifact_type,
            location=evidence_input.location,
            extraction_method=evidence_input.extraction_method,
            extractor_version=evidence_input.extractor_version,
        )

        return EvidenceObject(
            evidence_id=uuid4(),
            evidence_type=evidence_input.evidence_type,
            content=evidence_input.content,
            structured_content=evidence_input.structured_content,
            confidence=evidence_input.confidence,
            provenance=provenance,
            extracted_at=datetime.now(timezone.utc),
            metadata=evidence_input.metadata,
        )