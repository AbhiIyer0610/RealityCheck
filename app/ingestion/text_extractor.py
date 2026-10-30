from app.ingestion.extractors import Extractor
from app.ingestion.models import (
    Artifact,
    ExtractedElement,
    ExtractedElementType,
    ExtractionResult,
    ExtractionStatus,
)
from app.ingestion.sources import ArtifactSource


class TextExtractor(Extractor):
    @property
    def name(self) -> str:
        return "text-extractor"

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

        content = data.decode("utf-8")

        return ExtractionResult(
            artifact_id=artifact.artifact_id,
            status=ExtractionStatus.SUCCESS,
            extractor_name=self.name,
            extractor_version=self.version,
            elements=[
                ExtractedElement(
                    element_type=ExtractedElementType.TEXT,
                    content=content,
                    extraction_confidence=1.0,
                )
            ],
        )