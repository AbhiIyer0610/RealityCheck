from app.evidence.models import (
    ArtifactType,
    EvidenceObject,
    EvidenceProvenance,
    EvidenceType,
)
from app.core.provenance import EvidenceLocation


def test_create_pdf_evidence():
    evidence = EvidenceObject(
        evidence_type=EvidenceType.INTENT,
        content="Customers may request a refund within 30 days.",
        confidence=0.96,
        provenance=EvidenceProvenance(
            source_id="artifact-001",
            source_name="refund_policy.pdf",
            artifact_type=ArtifactType.PDF,
            location=EvidenceLocation(page=4),
            extraction_method="pdf_text_extraction",
            extractor_version="0.1.0",
        ),
    )

    assert evidence.evidence_type == EvidenceType.INTENT
    assert evidence.content == (
        "Customers may request a refund within 30 days."
    )
    assert evidence.confidence == 0.96
    assert evidence.provenance.source_name == "refund_policy.pdf"
    assert evidence.provenance.location.page == 4
    assert evidence.evidence_id is not None
    assert evidence.extracted_at.tzinfo is not None


def test_create_code_evidence():
    evidence = EvidenceObject(
        evidence_type=EvidenceType.IMPLEMENTATION,
        content="if days_since_purchase > 14: reject_refund()",
        confidence=0.99,
        provenance=EvidenceProvenance(
            source_id="artifact-002",
            source_name="refund_service.py",
            artifact_type=ArtifactType.CODE,
            location=EvidenceLocation(
                line_start=81,
                line_end=87,
            ),
            extraction_method="code_parser",
            extractor_version="0.1.0",
        ),
    )

    assert evidence.provenance.artifact_type == ArtifactType.CODE
    assert evidence.provenance.location.line_start == 81
    assert evidence.provenance.location.line_end == 87


def test_create_image_evidence():
    evidence = EvidenceObject(
        evidence_type=EvidenceType.IMPLEMENTATION,
        content="Refund service routes requests through the 14-day policy node.",
        confidence=0.88,
        provenance=EvidenceProvenance(
            source_id="artifact-003",
            source_name="architecture.png",
            artifact_type=ArtifactType.IMAGE,
            location=EvidenceLocation(
                page=None,
                bounding_box={
                    "x1": 0.20,
                    "y1": 0.30,
                    "x2": 0.75,
                    "y2": 0.60,
                },
            ),
            extraction_method="vision_model",
            extractor_version="0.1.0",
        ),
    )

    assert evidence.provenance.artifact_type == ArtifactType.IMAGE
    assert evidence.provenance.location.bounding_box.x1 == 0.20