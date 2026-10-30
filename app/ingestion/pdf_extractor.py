from importlib.metadata import version as package_version

from app.core.config import settings
from app.ingestion.extraction_runtime import (
    DoclingExtractionRuntime,
    ExtractionWorkerError,
)
from app.ingestion.models import (
    Artifact,
    ExtractionDiagnostic,
    ExtractionResult,
    ExtractionStatus,
)
from app.ingestion.sources import ArtifactSource


class PDFExtractor:
    def __init__(
        self,
        runtime: DoclingExtractionRuntime | None = None,
    ) -> None:
        self._runtime = runtime or DoclingExtractionRuntime(
            max_concurrent_extractions=settings.max_concurrent_extractions,
        )
        self._owns_runtime = runtime is None

    @property
    def name(self) -> str:
        return "docling-pdf"

    @property
    def version(self) -> str:
        return package_version("docling")

    def supports(self, artifact: Artifact) -> bool:
        return artifact.media_type == "application/pdf"

    async def extract(
        self,
        artifact: Artifact,
        source: ArtifactSource,
    ) -> ExtractionResult:
        if not self.supports(artifact):
            raise ValueError(
                f"{self.name} does not support media type "
                f"{artifact.media_type!r}."
            )

        try:
            pdf_bytes = await source.read()
        except OSError as exc:
            return self._failed_result(
                artifact=artifact,
                message=f"Could not read the PDF source: {exc}",
                diagnostic_code="source_read_failed",
            )

        try:
            return await self._runtime.extract_pdf(
                filename=artifact.filename,
                pdf_bytes=pdf_bytes,
                artifact_id=artifact.artifact_id,
                extractor_version=self.version,
            )
        except ExtractionWorkerError as exc:
            return self._failed_result(
                artifact=artifact,
                message=f"PDF extraction worker failed: {exc}",
                diagnostic_code="extraction_worker_failed",
            )

    async def shutdown(self) -> None:
        """Shut down the runtime only when this extractor owns it."""
        if self._owns_runtime:
            await self._runtime.shutdown()

    def _failed_result(
        self,
        artifact: Artifact,
        message: str,
        diagnostic_code: str,
    ) -> ExtractionResult:
        return ExtractionResult(
            artifact_id=artifact.artifact_id,
            status=ExtractionStatus.FAILED,
            diagnostics=[
                ExtractionDiagnostic(
                    message=message,
                    severity="error",
                    metadata={
                        "source": "realitycheck",
                        "diagnostic_code": diagnostic_code,
                    },
                )
            ],
            extractor_name=self.name,
            extractor_version=self.version,
        )