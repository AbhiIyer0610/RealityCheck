from app.evidence.factory import EvidenceFactory
from app.evidence.inputs import EvidenceInput
from app.evidence.models import (
    ArtifactType,
    EvidenceType,
)
from app.core.provenance import EvidenceLocation


def test_factory_creates_pdf_evidence():
    evidence_input = EvidenceInput(
        source_id="artifact-pdf-001",
        source_name="refund_policy.pdf",
        artifact_type=ArtifactType.PDF,
        content="Customers may request a refund within 30 days.",
        evidence_type=EvidenceType.INTENT,
        confidence=0.96,
        location=EvidenceLocation(page=4),
        extraction_method="pdf_text_extraction",
        extractor_version="0.1.0",
    )

    evidence = EvidenceFactory.create(evidence_input)

    assert evidence.provenance.source_id == "artifact-pdf-001"
    assert evidence.provenance.source_name == "refund_policy.pdf"
    assert evidence.provenance.artifact_type == ArtifactType.PDF
    assert evidence.provenance.location.page == 4
    assert evidence.provenance.extraction_method == "pdf_text_extraction"

    assert evidence.content == evidence_input.content
    assert evidence.evidence_type == EvidenceType.INTENT
    assert evidence.confidence == 0.96


def test_factory_creates_code_evidence():
    evidence_input = EvidenceInput(
        source_id="artifact-code-001",
        source_name="refund_service.py",
        artifact_type=ArtifactType.CODE,
        content="if days_since_purchase > 14: reject_refund()",
        evidence_type=EvidenceType.IMPLEMENTATION,
        confidence=0.99,
        location=EvidenceLocation(
            line_start=81,
            line_end=87,
        ),
        extraction_method="code_parser",
        extractor_version="0.1.0",
    )

    evidence = EvidenceFactory.create(evidence_input)

    assert evidence.provenance.source_id == "artifact-code-001"
    assert evidence.provenance.source_name == "refund_service.py"
    assert evidence.provenance.artifact_type == ArtifactType.CODE
    assert evidence.provenance.location.line_start == 81
    assert evidence.provenance.location.line_end == 87

    assert evidence.evidence_type == EvidenceType.IMPLEMENTATION


def test_factory_creates_image_evidence():
    evidence_input = EvidenceInput(
        source_id="artifact-image-001",
        source_name="architecture.png",
        artifact_type=ArtifactType.IMAGE,
        content="Refund service routes requests through the 14-day policy node.",
        evidence_type=EvidenceType.IMPLEMENTATION,
        confidence=0.88,
        location=EvidenceLocation(
            bounding_box={
                "x1": 0.20,
                "y1": 0.30,
                "x2": 0.75,
                "y2": 0.60,
            }
        ),
        extraction_method="vision_model",
        extractor_version="0.1.0",
    )

    evidence = EvidenceFactory.create(evidence_input)

    assert evidence.provenance.source_id == "artifact-image-001"
    assert evidence.provenance.source_name == "architecture.png"
    assert evidence.provenance.artifact_type == ArtifactType.IMAGE

    assert evidence.provenance.location.bounding_box.x1 == 0.20
    assert evidence.provenance.location.bounding_box.y2 == 0.60

    assert evidence.evidence_type == EvidenceType.IMPLEMENTATION


def test_factory_generates_unique_evidence_ids():
    evidence_input = EvidenceInput(
        source_id="artifact-001",
        source_name="refund_policy.pdf",
        artifact_type=ArtifactType.PDF,
        content="Customers may request a refund within 30 days.",
        evidence_type=EvidenceType.INTENT,
        confidence=0.96,
        extraction_method="pdf_text_extraction",
    )

    evidence_one = EvidenceFactory.create(evidence_input)
    evidence_two = EvidenceFactory.create(evidence_input)

    assert evidence_one.evidence_id != evidence_two.evidence_id