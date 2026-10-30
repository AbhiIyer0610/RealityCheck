from app.evidence.factory import EvidenceFactory
from app.evidence.models import EvidenceObject, EvidenceType
from app.ingestion.extractors import Extractor
from app.ingestion.sources import ArtifactSource
from app.ingestion.models import Artifact, ExtractionResult
from app.ingestion.extraction_evidence_mapper import ExtractionEvidenceMapper


class IngestionService:
    def __init__(self, extractor: Extractor) -> None:
        self._extractor = extractor

    async def extract(
        self,
        artifact: Artifact,
        source: ArtifactSource,
    ) -> ExtractionResult:
        if not self._extractor.supports(artifact):
            raise ValueError(
                f"Extractor '{self._extractor.name}' does not support "
                f"media type '{artifact.media_type}'."
            )

        return await self._extractor.extract(
            artifact=artifact,
            source=source,
        )

    async def extract_with_evidence(
        self,
        artifact: Artifact,
        source: ArtifactSource,
        evidence_type: EvidenceType = EvidenceType.UNKNOWN,
    ) -> tuple[ExtractionResult, list[EvidenceObject]]:
        """Extract once and return both the extraction result and mapped evidence."""
        extraction_result = await self.extract(
            artifact=artifact,
            source=source,
        )

        evidence_objects: list[EvidenceObject] = []
        for element in extraction_result.elements:
            evidence_input = ExtractionEvidenceMapper.to_evidence_input(
                artifact=artifact,
                element=element,
                extraction_result=extraction_result,
                evidence_type=evidence_type,
            )
            evidence_objects.append(EvidenceFactory.create(evidence_input))

        return extraction_result, evidence_objects

    async def extract_evidence(
        self,
        artifact: Artifact,
        source: ArtifactSource,
        evidence_type: EvidenceType = EvidenceType.UNKNOWN,
    ) -> list[EvidenceObject]:
        """Compatibility convenience method returning only mapped evidence."""
        _, evidence_objects = await self.extract_with_evidence(
            artifact=artifact,
            source=source,
            evidence_type=evidence_type,
        )
        return evidence_objects
