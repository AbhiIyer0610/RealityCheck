import pytest
from pydantic import ValidationError

from app.evidence.inputs import EvidenceInput
from app.evidence.models import ArtifactType, EvidenceType


def test_create_pdf_evidence_input():
    evidence_input = EvidenceInput(
        source_id="artifact-001",
        source_name="refund_policy.pdf",
        artifact_type=ArtifactType.PDF,
        content="Customers may request a refund within 30 days.",
        evidence_type=EvidenceType.INTENT,
        confidence=0.96,
        extraction_method="pdf_text_extraction",
        extractor_version="0.1.0",
    )

    assert evidence_input.source_id == "artifact-001"
    assert evidence_input.artifact_type == ArtifactType.PDF
    assert evidence_input.confidence == 0.96


def test_invalid_confidence_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceInput(
            source_id="artifact-001",
            source_name="refund_policy.pdf",
            artifact_type=ArtifactType.PDF,
            content="Some evidence",
            confidence=1.5,
            extraction_method="pdf_text_extraction",
        )


def test_empty_content_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceInput(
            source_id="artifact-001",
            source_name="refund_policy.pdf",
            artifact_type=ArtifactType.PDF,
            content="",
            extraction_method="pdf_text_extraction",
        )