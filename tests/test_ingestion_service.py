import pytest

from app.evidence.models import EvidenceType
from app.ingestion.service import IngestionService
from app.ingestion.text_extractor import TextExtractor
from app.ingestion.models import Artifact, ArtifactStatus


class MemoryArtifactSource:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_ingestion_service_extracts_artifact() -> None:
    artifact = Artifact(
        filename="policy.txt",
        media_type="text/plain",
        size_bytes=34,
        status=ArtifactStatus.RECEIVED,
    )

    source = MemoryArtifactSource(
        b"Refunds are allowed within 30 days."
    )

    service = IngestionService(
        extractor=TextExtractor()
    )

    result = await service.extract(
        artifact=artifact,
        source=source,
    )

    assert result.artifact_id == artifact.artifact_id
    assert result.status.value == "success"
    assert len(result.elements) == 1
    assert result.elements[0].content == (
        "Refunds are allowed within 30 days."
    )

@pytest.mark.asyncio
async def test_ingestion_service_creates_evidence() -> None:
    artifact = Artifact(
        filename="refund_policy.txt",
        media_type="text/plain",
        size_bytes=34,
        status=ArtifactStatus.RECEIVED,
    )

    source = MemoryArtifactSource(
        b"Refunds are allowed within 30 days."
    )

    service = IngestionService(
        extractor=TextExtractor()
    )

    evidence_objects = await service.extract_evidence(
        artifact=artifact,
        source=source,
        evidence_type=EvidenceType.INTENT,
    )

    assert len(evidence_objects) == 1

    evidence = evidence_objects[0]

    assert evidence.evidence_type == EvidenceType.INTENT
    assert evidence.content == (
        "Refunds are allowed within 30 days."
    )
    assert evidence.provenance.source_id == str(
        artifact.artifact_id
    )
    assert evidence.provenance.source_name == artifact.filename
    assert evidence.provenance.artifact_type.value == "text"

    assert evidence.provenance.extraction_method == "text-extractor"
    assert evidence.provenance.extractor_version == "0.1.0"

@pytest.mark.asyncio
async def test_ingestion_service_rejects_unsupported_artifact() -> None:
    artifact = Artifact(
        filename="policy.pdf",
        media_type="application/pdf",
        size_bytes=100,
        status=ArtifactStatus.RECEIVED,
    )

    source = MemoryArtifactSource(b"not really a pdf")

    service = IngestionService(
        extractor=TextExtractor()
    )

    with pytest.raises(ValueError, match="does not support"):
        await service.extract(
            artifact=artifact,
            source=source,
        )