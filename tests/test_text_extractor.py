import pytest

from app.ingestion.models import (
    Artifact,
    ArtifactStatus,
    ExtractionStatus,
    ExtractedElementType,
)
from app.ingestion.text_extractor import TextExtractor


class MemoryArtifactSource:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_text_extractor_extracts_plain_text() -> None:
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

    result = await extractor.extract(artifact, source)

    assert result.artifact_id == artifact.artifact_id
    assert result.status == ExtractionStatus.SUCCESS
    assert result.extractor_name == "text-extractor"
    assert result.extractor_version == "0.1.0"

    assert len(result.elements) == 1

    element = result.elements[0]

    assert element.element_type == ExtractedElementType.TEXT
    assert element.content == "Refunds are allowed within 30 days."
    assert element.extraction_confidence == 1.0


@pytest.mark.asyncio
async def test_text_extractor_supports_only_plain_text() -> None:
    extractor = TextExtractor()

    text_artifact = Artifact(
        filename="policy.txt",
        media_type="text/plain",
        size_bytes=10,
    )

    pdf_artifact = Artifact(
        filename="policy.pdf",
        media_type="application/pdf",
        size_bytes=10,
    )

    assert extractor.supports(text_artifact)
    assert not extractor.supports(pdf_artifact)