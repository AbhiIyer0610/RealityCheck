from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Mapping
from uuid import UUID, uuid4

from app.core.config import Settings
from app.evidence.models import EvidenceType
from app.ingestion.models import (
    Artifact,
    ArtifactStatus,
    ExtractionDiagnostic,
    ExtractionResult,
    ExtractionStatus,
)
from app.ingestion.service import IngestionService
from app.ingestion.sources import ArtifactSource
from app.ingestion.text_extractor import TextExtractor
from app.ingestion.extractors import Extractor
from app.jobs.models import JobStatus, StoredJob
from app.jobs.store import JobStore
from app.reasoning.models import AnalysisStatus
from app.reasoning.factory import create_claim_analyzer
from app.reasoning.interfaces import ClaimAnalysisError, ClaimAnalyzer
from app.reasoning.validation import validate_analysis_results
from app.reasoning.comparison import (
    ComparisonDocument, ComparisonResponse, EvidenceSourceReference,
)

if TYPE_CHECKING:
    from app.ingestion.extraction_runtime import DoclingExtractionRuntime

logger = logging.getLogger(__name__)


class JobQueueFull(RuntimeError):
    """Raised when the bounded pending-job queue has no capacity."""


class JobManagerNotStarted(RuntimeError):
    """Raised if a job is submitted before application startup completes."""


class ComparisonNotConfigured(RuntimeError):
    """Raised when no claim-analysis provider is configured."""


class ComparisonJobNotFound(LookupError):
    """Raised when a requested source job does not exist."""


class ComparisonNotReady(RuntimeError):
    """Raised when a selected job has no completed claims to compare."""


class ComparisonAnalysisFailed(RuntimeError):
    """Raised when combined reconciliation fails safely."""


class StoredArtifactSource(ArtifactSource):
    def __init__(self, path: Path) -> None:
        self._path = path

    async def read(self) -> bytes:
        return await asyncio.to_thread(self._path.read_bytes)


class JobManager:
    """Owns the bounded in-process queue and persists job state in SQLite."""

    def __init__(
        self,
        settings: Settings,
        *,
        extractors: Mapping[str, Extractor] | None = None,
        claim_analyzer: ClaimAnalyzer | None = None,
    ) -> None:
        self._settings = settings
        self._data_dir = settings.data_dir.expanduser().resolve()
        self._store = JobStore(self._data_dir / "realitycheck.sqlite3")
        self._queue: asyncio.Queue[UUID | None] = asyncio.Queue(
            maxsize=settings.max_pending_extraction_jobs
        )
        self._workers: list[asyncio.Task[None]] = []
        self._started = False
        self._stopping = False
        self._runtime: DoclingExtractionRuntime | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._claim_analyzer = claim_analyzer if claim_analyzer is not None else create_claim_analyzer(settings)
        self._analysis_provider = (
            getattr(self._claim_analyzer, "provider_name", "custom")
            if self._claim_analyzer is not None else "disabled"
        )

        if extractors is None:
            # Import the heavyweight Docling stack only for the production extractor set.
            from app.ingestion.extraction_runtime import DoclingExtractionRuntime
            from app.ingestion.pdf_extractor import PDFExtractor

            self._runtime = DoclingExtractionRuntime(
                max_concurrent_extractions=settings.max_concurrent_extractions
            )
            self._extractors: dict[str, Extractor] = {
                "application/pdf": PDFExtractor(runtime=self._runtime),
                "text/plain": TextExtractor(),
            }
        else:
            self._extractors = dict(extractors)

    @property
    def is_started(self) -> bool:
        return self._started and not self._stopping

    async def start(self) -> None:
        if self._started:
            return

        await asyncio.to_thread(
            self._data_dir.mkdir,
            parents=True,
            exist_ok=True,
        )
        artifact_dir = self._data_dir / "artifacts"
        await asyncio.to_thread(
            artifact_dir.mkdir,
            parents=True,
            exist_ok=True,
        )
        await self._store.initialize()
        await self._store.recover_interrupted_jobs()
        await self._cleanup_expired_jobs()
        await self._cleanup_orphaned_artifacts()
        if self._claim_analyzer is not None:
            await self._claim_analyzer.start()

        pending_jobs = await self._store.list_pending_jobs()
        for job in pending_jobs:
            if not job.artifact_path.is_file():
                await self._store.fail_unstarted_job(
                    job.job_id,
                    "The stored artifact is missing; please upload it again.",
                )
                continue
            try:
                self._queue.put_nowait(job.job_id)
            except asyncio.QueueFull:
                await self._store.fail_unstarted_job(
                    job.job_id,
                    "The pending-job capacity was exceeded during recovery. Please upload the artifact again.",
                )

        self._stopping = False
        self._started = True
        self._cleanup_task = asyncio.create_task(
            self._retention_cleanup_loop(), name="realitycheck-retention-cleanup"
        )
        self._workers = [
            asyncio.create_task(
                self._worker_loop(),
                name=f"realitycheck-job-worker-{index}",
            )
            for index in range(self._settings.max_concurrent_extractions)
        ]

    async def submit(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> StoredJob:
        if not self.is_started:
            raise JobManagerNotStarted("The extraction job manager is not ready.")
        if media_type not in self._extractors:
            raise ValueError(f"No extractor is registered for {media_type!r}.")

        now = datetime.now(timezone.utc)
        job_id = uuid4()
        artifact_id = uuid4()
        extension_by_media_type = {
            "application/pdf": ".pdf",
            "text/plain": ".txt",
        }
        extension = extension_by_media_type.get(media_type)
        if extension is None:
            raise ValueError(f"No storage extension is configured for {media_type!r}.")
        artifact_path = self._data_dir / "artifacts" / f"{job_id}{extension}"
        job = StoredJob(
            job_id=job_id,
            artifact_id=artifact_id,
            filename=filename,
            media_type=media_type,
            size_bytes=len(content),
            status=JobStatus.PENDING,
            created_at=now,
            artifact_path=artifact_path,
            analysis_provider=self._analysis_provider,
        )

        await asyncio.to_thread(_write_file_atomically, artifact_path, content)
        try:
            await self._store.create_job(job)
        except Exception:
            await asyncio.to_thread(_delete_file_if_present, artifact_path)
            raise

        try:
            self._queue.put_nowait(job_id)
        except asyncio.QueueFull as exc:
            await self._store.delete_job(job_id)
            await asyncio.to_thread(_delete_file_if_present, artifact_path)
            raise JobQueueFull(
                "The extraction queue is full. Try again when a running job finishes."
            ) from exc

        return job

    async def get_job(self, job_id: UUID) -> StoredJob | None:
        return await self._store.get_job(job_id)

    async def list_history_jobs(self) -> list[StoredJob]:
        return await self._store.list_jobs()

    async def list_history_comparisons(self) -> list[ComparisonResponse]:
        return await self._store.list_comparisons()

    async def delete_history_job(self, job_id: UUID) -> bool:
        job = await self._store.get_job(job_id)
        if job is None:
            return False
        if not job.status.is_terminal:
            raise ValueError("An active job cannot be deleted. Wait until processing finishes.")
        deleted = await self._store.delete_completed_job(job_id)
        if deleted:
            await asyncio.to_thread(_delete_file_if_present, job.artifact_path)
        return deleted

    async def delete_history_comparison(self, comparison_id: UUID) -> bool:
        """Delete a comparison and source jobs no longer referenced by saved comparisons."""
        comparison = await self._store.get_comparison(comparison_id)
        if comparison is None:
            return False

        deleted = await self._store.delete_comparison(comparison_id)
        if not deleted:
            return False

        remaining_comparisons = await self._store.list_comparisons()
        referenced_job_ids = {
            document.job_id
            for saved_comparison in remaining_comparisons
            for document in saved_comparison.documents
        }
        for document in comparison.documents:
            if document.job_id in referenced_job_ids:
                continue
            job = await self._store.get_job(document.job_id)
            if job is None or not job.status.is_terminal:
                continue
            if await self._store.delete_completed_job(document.job_id):
                await asyncio.to_thread(_delete_file_if_present, job.artifact_path)

        return True

    async def get_evidence(self, job_id: UUID) -> StoredJob | None:
        return await self._store.get_job(job_id)

    async def compare_jobs(self, job_ids: list[UUID]) -> ComparisonResponse:
        """Compare claims from 2-10 completed jobs and persist the combined result."""
        if not self.is_started:
            raise JobManagerNotStarted("The analysis service is not ready.")
        if self._claim_analyzer is None:
            raise ComparisonNotConfigured(
                "Claim analysis is not configured. Set ANALYSIS_PROVIDER=offline for heuristic demo comparison, "
                "or configure Nebius Token Factory."
            )
        if not 2 <= len(job_ids) <= 10:
            raise ValueError("Select between 2 and 10 documents to compare.")
        if len(set(job_ids)) != len(job_ids):
            raise ValueError("Each document must refer to a different job.")

        jobs: list[StoredJob] = []
        for job_id in job_ids:
            job = await self._store.get_job(job_id)
            if job is None:
                raise ComparisonJobNotFound(f"Job {job_id} was not found. It may have expired.")
            if not job.status.is_terminal or job.status == JobStatus.FAILED:
                raise ComparisonNotReady(
                    f"'{job.filename}' has not completed successfully. Wait for extraction before comparing."
                )
            if job.analysis_status != AnalysisStatus.SUCCEEDED:
                raise ComparisonNotReady(
                    f"'{job.filename}' does not have completed claims. Check its analysis status before comparing."
                )
            jobs.append(job)

        evidence = [item for job in jobs for item in job.evidence]
        claims = [item for job in jobs for item in job.claims]
        if not evidence or not claims:
            raise ComparisonNotReady("The selected documents do not contain enough extracted evidence and claims to compare.")
        total_claim_chars = sum(len(claim.text) for claim in claims)
        if len(claims) > 120 or len(evidence) > 1000 or total_claim_chars > self._settings.max_analysis_input_chars:
            raise ValueError(
                "The selected documents produced too much content for one comparison. "
                "Compare fewer documents or split the sources into smaller sets."
            )

        compare_method = getattr(self._claim_analyzer, "compare_documents", None)
        try:
            if callable(compare_method):
                findings = await asyncio.wait_for(
                    compare_method(evidence, claims),
                    timeout=self._settings.llm_timeout_seconds + 10,
                )
                mode = "offline_heuristic" if self._analysis_provider == "offline_demo" else "model_reconciliation"
            else:
                findings = await asyncio.wait_for(
                    self._claim_analyzer.reconcile(evidence, claims),
                    timeout=self._settings.llm_timeout_seconds + 10,
                )
                mode = "model_reconciliation"
        except asyncio.TimeoutError as exc:
            raise ComparisonAnalysisFailed("Cross-document analysis timed out. Try fewer documents.") from exc
        except Exception as exc:
            logger.exception("Cross-document analysis failed")
            raise ComparisonAnalysisFailed(
                "Cross-document analysis failed. Your uploaded evidence and individual job results remain available."
            ) from exc

        valid_claims, valid_findings = validate_analysis_results(evidence, claims, findings)
        if len(valid_claims) != len(claims):
            # Per-document claims were already validated when saved. A difference here is
            # a defensive signal; never silently let invalid cross-document references pass.
            raise ComparisonAnalysisFailed("Some source claims failed traceability validation; comparison was not saved.")

        now = datetime.now(timezone.utc)
        evidence_sources = []
        seen_evidence: set[UUID] = set()
        for item in evidence:
            if item.evidence_id in seen_evidence:
                continue
            seen_evidence.add(item.evidence_id)
            content = item.content or (str(item.structured_content) if item.structured_content else "")
            preview = " ".join(content.split())[:360]
            evidence_sources.append(EvidenceSourceReference(
                evidence_id=item.evidence_id,
                source_name=item.provenance.source_name,
                source_id=item.provenance.source_id,
                preview=preview,
            ))

        result = ComparisonResponse(
            comparison_id=uuid4(),
            created_at=now,
            analysis_provider=self._analysis_provider,
            mode=mode,
            documents=[ComparisonDocument(
                job_id=job.job_id, filename=job.filename, status=job.status,
                analysis_provider=job.analysis_provider,
            ) for job in jobs],
            claims=valid_claims,
            findings=valid_findings,
            evidence_sources=evidence_sources,
        )
        await self._store.save_comparison(result)
        return result

    async def get_comparison(self, comparison_id: UUID) -> ComparisonResponse | None:
        return await self._store.get_comparison(comparison_id)

    async def health_check(self) -> bool:
        return self.is_started and await self._store.health_check()

    async def shutdown(self) -> None:
        if not self._started:
            if self._runtime is not None:
                await self._runtime.shutdown()
            if self._claim_analyzer is not None:
                await self._claim_analyzer.close()
            return
        self._stopping = True

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None

        # Sentinels follow queued work, so a graceful shutdown drains accepted jobs.
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        if self._runtime is not None:
            await self._runtime.shutdown()
        if self._claim_analyzer is not None:
            await self._claim_analyzer.close()

        self._started = False

    async def _retention_cleanup_loop(self) -> None:
        """Periodically remove old terminal jobs and their source artifacts."""
        interval = self._settings.job_cleanup_interval_seconds
        while True:
            try:
                await asyncio.sleep(interval)
                await self._cleanup_expired_jobs()
                await self._cleanup_orphaned_artifacts()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Retention cleanup failed; it will retry next interval")

    async def _cleanup_expired_jobs(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._settings.job_retention_days)
        await self._store.delete_expired_comparisons(cutoff)
        expired_jobs = await self._store.list_expired_terminal_jobs(cutoff)
        for job in expired_jobs:
            removed = await asyncio.to_thread(_remove_artifact_for_retention, job.artifact_path)
            if not removed:
                continue
            deleted = await self._store.delete_expired_job(job.job_id, cutoff)
            if deleted:
                await self._store.delete_comparisons_for_job(job.job_id)
                logger.info("Expired job %s and its artifact were removed", job.job_id)

    async def _cleanup_orphaned_artifacts(self) -> None:
        """Remove abandoned temp files and artifacts no longer referenced by SQLite."""
        artifact_dir = self._data_dir / "artifacts"
        if not artifact_dir.exists():
            return
        referenced = await self._store.list_referenced_artifact_paths()
        entries = await asyncio.to_thread(lambda: list(artifact_dir.iterdir()))
        cutoff_timestamp = time.time() - self._settings.orphan_artifact_grace_seconds
        for path in entries:
            if not path.is_file():
                continue
            try:
                modified_at = (await asyncio.to_thread(path.stat)).st_mtime
            except OSError:
                logger.exception("Could not inspect artifact file %s; it will be retried", path)
                continue
            # A grace period avoids racing an upload between atomic file placement and DB commit.
            if modified_at > cutoff_timestamp:
                continue
            resolved = path.resolve()
            if path.name.endswith(".tmp") or resolved not in referenced:
                try:
                    await asyncio.to_thread(path.unlink, missing_ok=True)
                    logger.info("Removed orphaned artifact file %s", path.name)
                except OSError:
                    logger.exception("Could not remove orphaned artifact file %s; it will be retried", path)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if job_id is None:
                    return
                await self._process_job(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unhandled error in extraction worker loop")
            finally:
                self._queue.task_done()

    async def _process_job(self, job_id: UUID) -> None:
        job = await self._store.get_job(job_id)
        if job is None or job.status != JobStatus.PENDING:
            return

        extractor = self._extractors.get(job.media_type)
        if extractor is None:
            await self._store.fail_unstarted_job(
                job_id, f"No extractor is registered for {job.media_type!r}."
            )
            return
        if not await self._store.mark_running(job_id):
            return

        artifact = Artifact(
            artifact_id=job.artifact_id,
            filename=job.filename,
            media_type=job.media_type,
            size_bytes=job.size_bytes,
            status=ArtifactStatus.PROCESSING,
            received_at=job.created_at,
        )
        service = IngestionService(extractor=extractor)
        try:
            result, evidence = await asyncio.wait_for(
                service.extract_with_evidence(
                    artifact=artifact,
                    source=StoredArtifactSource(job.artifact_path),
                    evidence_type=EvidenceType.UNKNOWN,
                ),
                timeout=self._settings.max_extraction_duration_seconds,
            )
            await self._store.save_extraction_stage(
                job_id, result, evidence,
                processing_stage="extracting_claims" if self._claim_analyzer and result.status != ExtractionStatus.FAILED else "complete",
                progress_message=(
                    ("Offline demo: extracting source-linked claims." if self._analysis_provider == "offline_demo"
                     else "Evidence extracted. Identifying explicit claims.")
                    if self._claim_analyzer and result.status != ExtractionStatus.FAILED
                    else "Evidence extraction finished."
                ),
            )

            if result.status != ExtractionStatus.FAILED and self._claim_analyzer is not None:
                await self._store.update_analysis_progress(
                    job_id,
                    processing_stage="extracting_claims",
                    progress_message=(
                        "OFFLINE DEMO (simulated; no model calls): creating source-linked claims."
                        if self._analysis_provider == "offline_demo"
                        else "Evidence extracted. Identifying explicit and inferred claims with Nebius Token Factory."
                    ),
                    analysis_status=AnalysisStatus.RUNNING,
                )
                try:
                    claims = await asyncio.wait_for(
                        self._claim_analyzer.extract_claims(evidence),
                        timeout=self._settings.llm_timeout_seconds + 5,
                    )
                    # Validate before persisting/publishing the intermediate claim stage.
                    claims, _ = validate_analysis_results(evidence, claims, [])
                    await self._store.save_claims(job_id, claims)
                    await self._store.update_analysis_progress(
                        job_id,
                        processing_stage="reconciling_claims",
                        progress_message=f"Extracted {len(claims)} claims. Checking for evidence-backed mismatches.",
                    )
                    findings = await asyncio.wait_for(
                        self._claim_analyzer.reconcile(evidence, claims),
                        timeout=self._settings.llm_timeout_seconds + 5,
                    )
                    claims, findings = validate_analysis_results(evidence, claims, findings)
                    await self._store.save_claims(job_id, claims)
                    await self._store.save_findings(job_id, findings)
                    await self._store.finish_analysis(
                        job_id,
                        status=AnalysisStatus.SUCCEEDED,
                        progress_message=(
                            f"OFFLINE DEMO complete (simulated): {len(claims)} claims and {len(findings)} findings are ready."
                            if self._analysis_provider == "offline_demo"
                            else f"Analysis complete: {len(claims)} claims and {len(findings)} findings are ready."
                        ),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("AI analysis failed for job %s (%s)", job_id, type(exc).__name__)
                    safe_message = (
                        str(exc) if isinstance(exc, ClaimAnalysisError)
                        else "AI analysis could not be completed. Extracted evidence is still available."
                    )
                    await self._store.finish_analysis(
                        job_id,
                        status=AnalysisStatus.FAILED,
                        error_message=safe_message,
                        progress_message="Evidence extraction finished, but AI claim analysis failed. See the analysis status for details.",
                    )
            elif result.status == ExtractionStatus.FAILED:
                await self._store.finish_analysis(
                    job_id,
                    status=AnalysisStatus.FAILED,
                    error_message="Claim analysis was skipped because evidence extraction failed.",
                    progress_message="Evidence extraction failed; claim analysis was skipped.",
                )
            else:
                await self._store.update_analysis_progress(
                    job_id,
                    processing_stage="complete",
                    progress_message="Evidence extracted. Configure NEBIUS_API_KEY to enable claims and reconciliation findings.",
                    analysis_status=AnalysisStatus.NOT_CONFIGURED,
                )

            status = _job_status_for(result.status)
            error_message = None
            if status == JobStatus.FAILED:
                error_message = "Extraction failed. Review the extraction diagnostics."
            await self._store.complete_job(
                job_id=job_id,
                status=status,
                extraction_result=result,
                evidence=evidence,
                error_message=error_message,
            )
        except asyncio.TimeoutError:
            logger.warning("Extraction for job %s exceeded %s seconds", job_id, self._settings.max_extraction_duration_seconds)
            failed_result = ExtractionResult(
                artifact_id=job.artifact_id,
                status=ExtractionStatus.FAILED,
                elements=[],
                diagnostics=[ExtractionDiagnostic(
                    message="Extraction exceeded the configured processing deadline.",
                    severity="error",
                    metadata={"source": "realitycheck", "diagnostic_code": "extraction_timeout"},
                )],
                extractor_name=extractor.name,
                extractor_version=extractor.version,
            )
            await self._store.finish_analysis(
                job_id,
                status=AnalysisStatus.FAILED,
                error_message="Claim analysis was skipped because extraction timed out.",
                progress_message="Extraction timed out; claim analysis was skipped.",
            )
            await self._store.complete_job(
                job_id=job_id, status=JobStatus.FAILED,
                extraction_result=failed_result, evidence=[],
                error_message="Extraction exceeded the configured processing deadline.",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Extraction job %s failed unexpectedly", job_id)
            failed_result = ExtractionResult(
                artifact_id=job.artifact_id,
                status=ExtractionStatus.FAILED,
                elements=[],
                diagnostics=[ExtractionDiagnostic(
                    message="The extraction job failed unexpectedly.",
                    severity="error",
                    metadata={"source": "realitycheck", "diagnostic_code": "job_processing_failed"},
                )],
                extractor_name=extractor.name,
                extractor_version=extractor.version,
            )
            await self._store.complete_job(
                job_id=job_id, status=JobStatus.FAILED,
                extraction_result=failed_result, evidence=[],
                error_message="The extraction job failed unexpectedly.",
            )


def _job_status_for(status: ExtractionStatus) -> JobStatus:
    return {
        ExtractionStatus.SUCCESS: JobStatus.SUCCEEDED,
        ExtractionStatus.PARTIAL: JobStatus.PARTIAL,
        ExtractionStatus.FAILED: JobStatus.FAILED,
    }[status]


def _write_file_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary_path.open("wb") as file_handle:
            file_handle.write(content)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, path)
    finally:
        _delete_file_if_present(temporary_path)


def _delete_file_if_present(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove temporary artifact file %s", path)


def _remove_artifact_for_retention(path: Path) -> bool:
    """Remove an expired artifact; return False so cleanup can retry on OS errors."""
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        logger.exception("Could not remove expired artifact %s; retaining its job record", path)
        return False
