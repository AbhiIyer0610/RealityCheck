from app.evidence.factory import EvidenceFactory
from app.evidence.models import ArtifactType, EvidenceType
from app.ingestion.extraction_evidence_mapper import ExtractionEvidenceMapper
from app.ingestion.models import (
    Artifact,
    ExtractedElement,
    ExtractionResult,
    ExtractionStatus,
    ExtractedElementType,
)


def test_extracted_text_maps_to_evidence_input() -> None:
    artifact = Artifact(
        filename="refund_policy.txt",
        media_type="text/plain",
        size_bytes=34,
    )

    element = ExtractedElement(
        element_type=ExtractedElementType.TEXT,
        content="Refunds are allowed within 30 days.",
        extraction_confidence=0.98,
    )

    extraction_result = ExtractionResult(
        artifact_id=artifact.artifact_id,
        status=ExtractionStatus.SUCCESS,
        elements=[element],
        extractor_name="test-extractor",
        extractor_version="1.0.0",
    )

    evidence_input = ExtractionEvidenceMapper.to_evidence_input(
        artifact=artifact,
        element=element,
        extraction_result=extraction_result,
        evidence_type=EvidenceType.INTENT,
    )

    assert evidence_input.source_id == str(artifact.artifact_id)
    assert evidence_input.source_name == artifact.filename
    assert evidence_input.artifact_type == ArtifactType.TEXT
    assert evidence_input.evidence_type == EvidenceType.INTENT
    assert evidence_input.content == (
        "Refunds are allowed within 30 days."
    )
    assert evidence_input.confidence == 0.98
    assert evidence_input.location == element.location
    assert evidence_input.extraction_method == "test-extractor"
    assert evidence_input.extractor_version == "1.0.0"


def test_pdf_artifact_maps_to_pdf_artifact_type() -> None:
    artifact = Artifact(
        filename="refund_policy.pdf",
        media_type="application/pdf",
        size_bytes=100,
    )

    element = ExtractedElement(
        element_type=ExtractedElementType.TEXT,
        content="Refunds are allowed within 30 days.",
        extraction_confidence=0.95,
    )

    extraction_result = ExtractionResult(
        artifact_id=artifact.artifact_id,
        status=ExtractionStatus.SUCCESS,
        elements=[element],
        extractor_name="test-extractor",
        extractor_version="1.0.0",
    )

    evidence_input = ExtractionEvidenceMapper.to_evidence_input(
        artifact=artifact,
        element=element,
        extraction_result=extraction_result,
    )

    assert evidence_input.artifact_type == ArtifactType.PDF


def test_structured_table_maps_to_evidence_and_preserves_provenance() -> None:
    artifact = Artifact(
        filename="refund_policy.pdf",
        media_type="application/pdf",
        size_bytes=100,
    )

    structured_content = {
        "headers": ["Refund Type", "Window"],
        "rows": [["Standard", "30 days"]],
    }

    element = ExtractedElement(
        element_type=ExtractedElementType.TABLE,
        structured_content=structured_content,
        extraction_confidence=None,
    )

    extraction_result = ExtractionResult(
        artifact_id=artifact.artifact_id,
        status=ExtractionStatus.SUCCESS,
        elements=[element],
        extractor_name="docling-pdf",
        extractor_version="2.132.0",
    )

    evidence_input = ExtractionEvidenceMapper.to_evidence_input(
        artifact=artifact,
        element=element,
        extraction_result=extraction_result,
        evidence_type=EvidenceType.REQUIREMENT,
    )

    assert evidence_input.content is None
    assert evidence_input.structured_content == structured_content
    assert evidence_input.confidence is None
    assert evidence_input.artifact_type == ArtifactType.PDF

    evidence = EvidenceFactory.create(evidence_input)

    assert evidence.content is None
    assert evidence.structured_content == structured_content
    assert evidence.confidence is None
    assert evidence.evidence_type == EvidenceType.REQUIREMENT
    assert evidence.provenance.source_id == str(artifact.artifact_id)
    assert evidence.provenance.source_name == artifact.filename
    assert evidence.provenance.artifact_type == ArtifactType.PDF
    assert evidence.provenance.extraction_method == "docling-pdf"
    assert evidence.provenance.extractor_version == "2.132.0"
