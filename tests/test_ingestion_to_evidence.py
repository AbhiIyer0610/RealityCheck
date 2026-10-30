import pytest
from pathlib import Path

from app.evidence.factory import EvidenceFactory
from app.ingestion.service import IngestionService
from app.ingestion.pdf_extractor import PDFExtractor
from app.ingestion.text_extractor import TextExtractor
from app.evidence.models import EvidenceType, ArtifactType
from app.ingestion.extraction_evidence_mapper import ExtractionEvidenceMapper
from app.ingestion.models import Artifact, ArtifactStatus, ExtractionResult, ExtractionStatus


class MemoryArtifactSource:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_text_artifact_flows_to_evidence_object() -> None:
    artifact = Artifact(
        filename="refund_policy.txt",
        media_type="text/plain",
        size_bytes=34,
        status=ArtifactStatus.RECEIVED,
    )

    source = MemoryArtifactSource(
        b"Refunds are allowed within 30 days."
    )

    extractor = TextExtractor()

    extraction_result = await extractor.extract(
        artifact=artifact,
        source=source,
    )

    assert extraction_result.status.value == "success"
    assert len(extraction_result.elements) == 1

    element = extraction_result.elements[0]

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

    evidence = EvidenceFactory.create(evidence_input)

    assert evidence.evidence_type == EvidenceType.INTENT
    assert evidence.content == "Refunds are allowed within 30 days."
    assert evidence.confidence == 1.0

    assert evidence.provenance.source_id == str(artifact.artifact_id)
    assert evidence.provenance.source_name == artifact.filename

    assert evidence.provenance.extraction_method == "test-extractor"


@pytest.mark.asyncio
async def test_pdf_artifact_flows_through_ingestion_service_to_evidence() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "refund_policy.pdf"
    )
    pdf_bytes = fixture_path.read_bytes()

    artifact = Artifact(
        filename=fixture_path.name,
        media_type="application/pdf",
        size_bytes=len(pdf_bytes),
        status=ArtifactStatus.RECEIVED,
    )
    source = MemoryArtifactSource(pdf_bytes)

    extractor = PDFExtractor()
    service = IngestionService(extractor=extractor)

    try:
        evidence_objects = await service.extract_evidence(
            artifact=artifact,
            source=source,
            evidence_type=EvidenceType.UNKNOWN,
        )
    finally:
        await extractor.shutdown()

    # The fixture should produce two text elements and one table.
    assert len(evidence_objects) == 3

    text_evidence = [
        evidence
        for evidence in evidence_objects
        if evidence.content is not None
    ]
    table_evidence = [
        evidence
        for evidence in evidence_objects
        if evidence.structured_content is not None
    ]

    assert len(text_evidence) == 2
    assert len(table_evidence) == 1

    # Verify extracted text survives the complete pipeline.
    assert any(
        evidence.content == "Refund Policy"
        for evidence in text_evidence
    )
    assert any(
        evidence.content
        == "Customers may request a refund within 30 days of purchase."
        for evidence in text_evidence
    )

    # Verify structured table content survives without flattening.
    table = table_evidence[0]
    assert table.structured_content is not None
    assert "Standard" in str(table.structured_content)
    assert "30 days" in str(table.structured_content)

    # Verify the canonical evidence and source identity.
    for evidence in evidence_objects:
        assert evidence.evidence_type == EvidenceType.UNKNOWN
        assert evidence.provenance.source_id == str(artifact.artifact_id)
        assert evidence.provenance.source_name == artifact.filename
        assert evidence.provenance.artifact_type == ArtifactType.PDF
        assert evidence.provenance.extraction_method == "docling-pdf"
        assert evidence.provenance.extractor_version is not None
        assert evidence.provenance.extractor_version != ""
        assert evidence.confidence is None

    # Verify that element-level metadata is preserved.
    assert any(
        evidence.metadata.get("docling_label") == "section_header"
        for evidence in text_evidence
    )
    assert table.metadata.get("docling_label") == "table"
    assert table.metadata.get("rows") == 2
    assert table.metadata.get("columns") == 2

    # Verify source locations remain available and usable.
    for evidence in evidence_objects:
        location = evidence.provenance.location
        assert location is not None
        assert location.page == 1
        assert location.bounding_box is not None