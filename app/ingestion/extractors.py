from typing import Protocol

from app.ingestion.sources import ArtifactSource
from app.ingestion.models import Artifact, ExtractionResult


class Extractor(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def version(self) -> str:
        ...

    def supports(self, artifact: Artifact) -> bool:
        ...

    async def extract(
        self,
        artifact: Artifact,
        source: ArtifactSource,
    ) -> ExtractionResult:
        ...