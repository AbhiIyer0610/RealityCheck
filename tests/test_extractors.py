import pytest

from app.ingestion.models import (
    Artifact,
    ArtifactStatus,
    ExtractedElement,
    ExtractedElementType,
    ExtractionResult,
    ExtractionStatus,
)
from app.ingestion.sources import ArtifactSource


class MemoryArtifactSource:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class TestTextExtractor:
    @property
    def name(self) -> str:
        return "test-text-extractor"

    @property
    def version(self) -> str:
        return "0.1.0"

    def supports(self, artifact: Artifact) -> bool:
        return artifact.media_type == "text/plain"

    async def extract(
        self,
        artifact: Artifact,
        source: ArtifactSource,
    ) -> ExtractionResult:
        data = await source.read()

        return ExtractionResult(
            artifact_id=artifact.artifact_id,
            status=ExtractionStatus.SUCCESS,
            extractor_name=self.name,
            extractor_version=self.version,
            elements=[
                ExtractedElement(
                    element_type=ExtractedElementType.TEXT,
                    content=data.decode("utf-8"),
                    extraction_confidence=1.0,
                )
            ],
        )


@pytest.mark.asyncio
async def test_extractor_contract() -> None:
    artifact = Artifact(
        filename="policy.txt",
        media_type="text/plain",
        size_bytes=34,
        status=ArtifactStatus.RECEIVED,
    )

    source = MemoryArtifactSource(
        b"Refunds are allowed within 30 days."
    )

    extractor = TestTextExtractor()

    assert extractor.name == "test-text-extractor"
    assert extractor.version == "0.1.0"
    assert extractor.supports(artifact)

    result = await extractor.extract(artifact, source)

    assert result.artifact_id == artifact.artifact_id
    assert result.status == ExtractionStatus.SUCCESS
    assert len(result.elements) == 1
    assert result.elements[0].element_type == ExtractedElementType.TEXT
    assert result.elements[0].content == (
        "Refunds are allowed within 30 days."
    )