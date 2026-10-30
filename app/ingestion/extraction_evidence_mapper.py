
from app.evidence.inputs import EvidenceInput
from app.evidence.models import ArtifactType, EvidenceType
from app.ingestion.models import Artifact, ExtractedElement, ExtractionResult


class ExtractionEvidenceMapper:
    @staticmethod
    def to_evidence_input(
        artifact: Artifact,
        element: ExtractedElement,
        extraction_result: ExtractionResult,
        evidence_type: EvidenceType = EvidenceType.UNKNOWN,
    ) -> EvidenceInput:
        return EvidenceInput(
            source_id=str(artifact.artifact_id),
            source_name=artifact.filename,
            artifact_type=ExtractionEvidenceMapper._artifact_type(
                artifact.media_type
            ),
            content=element.content,
            structured_content=element.structured_content,
            evidence_type=evidence_type,
            confidence=element.extraction_confidence,
            location=element.location,
            extraction_method=extraction_result.extractor_name,
            extractor_version=extraction_result.extractor_version,
            metadata=element.metadata,
        )

    @staticmethod
    def _artifact_type(media_type: str) -> ArtifactType:
        if media_type == "text/plain":
            return ArtifactType.TEXT

        if media_type == "application/pdf":
            return ArtifactType.PDF

        if media_type.startswith("image/"):
            return ArtifactType.IMAGE

        return ArtifactType.UNKNOWN
