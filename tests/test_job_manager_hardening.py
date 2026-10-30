from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.evidence.models import EvidenceType
from app.ingestion.models import Artifact, ExtractionDiagnostic, ExtractionResult, ExtractionStatus
from app.ingestion.sources import ArtifactSource
from app.jobs.manager import JobManager
from app.jobs.models import JobStatus, StoredJob
from app.jobs.store import JobStore
from app.ingestion.text_extractor import TextExtractor


class SlowExtractor:
    name = "slow-test-extractor"
    version = "test"

    def supports(self, artifact: Artifact) -> bool:
        return artifact.media_type == "text/plain"

    async def extract(self, artifact: Artifact, source: ArtifactSource) -> ExtractionResult:
        await asyncio.sleep(0.2)
        return ExtractionResult(
            artifact_id=artifact.artifact_id, status=ExtractionStatus.SUCCESS,
            elements=[], extractor_name=self.name, extractor_version=self.version,
        )


@pytest.mark.asyncio
async def test_extraction_deadline_marks_job_failed_with_diagnostic(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, data_dir=tmp_path, max_concurrent_extractions=1,
        max_extraction_duration_seconds=0.02,
    )
    manager = JobManager(settings, extractors={"text/plain": SlowExtractor()})
    await manager.start()
    try:
        submitted = await manager.submit(filename="slow.txt", media_type="text/plain", content=b"slow")
        deadline = asyncio.get_running_loop().time() + 2
        current = submitted
        while asyncio.get_running_loop().time() < deadline:
            current = await manager.get_job(submitted.job_id)
            assert current is not None
            if current.status.is_terminal:
                break
            await asyncio.sleep(0.01)
        assert current.status == JobStatus.FAILED
        assert current.extraction_result is not None
        assert current.extraction_result.diagnostics[0].metadata["diagnostic_code"] == "extraction_timeout"
        assert current.processing_stage == "failed"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_startup_removes_orphaned_files_but_preserves_referenced_artifacts(tmp_path: Path) -> None:
    data_dir = tmp_path
    artifact_dir = data_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    keep_path = artifact_dir / f"{uuid4()}.txt"
    orphan_path = artifact_dir / "orphan.txt"
    temp_path = artifact_dir / "abandoned.txt.tmp"
    keep_path.write_text("referenced", encoding="utf-8")
    orphan_path.write_text("orphan", encoding="utf-8")
    temp_path.write_text("partial write", encoding="utf-8")

    store = JobStore(data_dir / "realitycheck.sqlite3")
    await store.initialize()
    now = datetime.now(timezone.utc)
    job = StoredJob(
        job_id=uuid4(), artifact_id=uuid4(), filename=keep_path.name, media_type="text/plain",
        size_bytes=10, status=JobStatus.SUCCEEDED, created_at=now, started_at=now,
        completed_at=now, artifact_path=keep_path,
    )
    await store.create_job(job)

    import os
    old_time = __import__("time").time() - 10
    for candidate in (keep_path, orphan_path, temp_path):
        os.utime(candidate, (old_time, old_time))
    settings = Settings(_env_file=None, data_dir=data_dir, max_concurrent_extractions=1,
                        orphan_artifact_grace_seconds=0)
    manager = JobManager(settings, extractors={"text/plain": TextExtractor()})
    await manager.start()
    try:
        assert keep_path.exists()
        assert not orphan_path.exists()
        assert not temp_path.exists()
    finally:
        await manager.shutdown()

class FakeClaimAnalyzer:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def extract_claims(self, evidence):
        from app.reasoning.models import Claim
        return [Claim(
            text="The source contains a testable requirement.", category="requirement", kind="explicit",
            evidence_ids=[evidence[0].evidence_id], confidence=0.91,
        )] if evidence else []

    async def reconcile(self, evidence, claims):
        await asyncio.sleep(0.2)
        from app.reasoning.models import Finding, FindingStatus
        return [Finding(
            title="Implementation evidence is not present",
            explanation="The uploaded source states a requirement, but no implementation evidence was supplied in this artifact.",
            status=FindingStatus.UNCERTAIN,
            evidence_ids=[evidence[0].evidence_id], claim_ids=[claims[0].claim_id], confidence=0.84,
            recommendation="Upload an implementation or observation artifact to test this requirement.",
        )] if evidence and claims else []


@pytest.mark.asyncio
async def test_pipeline_persists_claims_and_findings_and_updates_live_stage(tmp_path: Path) -> None:
    analyzer = FakeClaimAnalyzer()
    settings = Settings(_env_file=None, data_dir=tmp_path, max_concurrent_extractions=1)
    manager = JobManager(settings, extractors={"text/plain": TextExtractor()}, claim_analyzer=analyzer)
    await manager.start()
    try:
        submitted = await manager.submit(
            filename="requirements.txt", media_type="text/plain",
            content=b"The source contains a testable requirement.",
        )
        deadline = asyncio.get_running_loop().time() + 2
        current = submitted
        # Claims are persisted and observable while the second model stage is still running.
        while asyncio.get_running_loop().time() < deadline:
            current = await manager.get_job(submitted.job_id)
            assert current is not None
            if current.processing_stage == "reconciling_claims":
                break
            await asyncio.sleep(0.01)
        assert current.status == JobStatus.RUNNING
        assert len(current.claims) == 1
        assert current.findings == []

        while asyncio.get_running_loop().time() < deadline:
            current = await manager.get_job(submitted.job_id)
            assert current is not None
            if current.status.is_terminal:
                break
            await asyncio.sleep(0.01)

        assert current.status == JobStatus.SUCCEEDED
        assert current.analysis_status.value == "succeeded"
        assert len(current.claims) == 1
        assert len(current.findings) == 1
        assert current.findings[0].claim_ids == [current.claims[0].claim_id]
        assert current.processing_stage == "complete"
        assert analyzer.started is True
    finally:
        await manager.shutdown()
    assert analyzer.closed is True

class FailingClaimAnalyzer(FakeClaimAnalyzer):
    async def extract_claims(self, evidence):
        raise RuntimeError("simulated provider failure")


@pytest.mark.asyncio
async def test_ai_provider_failure_does_not_discard_successful_extraction(tmp_path: Path) -> None:
    analyzer = FailingClaimAnalyzer()
    settings = Settings(_env_file=None, data_dir=tmp_path, max_concurrent_extractions=1)
    manager = JobManager(settings, extractors={"text/plain": TextExtractor()}, claim_analyzer=analyzer)
    await manager.start()
    try:
        submitted = await manager.submit(
            filename="source.txt", media_type="text/plain", content=b"Evidence must remain available if the model fails."
        )
        deadline = asyncio.get_running_loop().time() + 2
        current = submitted
        while asyncio.get_running_loop().time() < deadline:
            current = await manager.get_job(submitted.job_id)
            assert current is not None
            if current.status.is_terminal:
                break
            await asyncio.sleep(0.01)
        assert current.status == JobStatus.SUCCEEDED
        assert current.extraction_result is not None
        assert len(current.evidence) == 1
        assert current.analysis_status.value == "failed"
        assert current.analysis_error_message == "AI analysis could not be completed. Extracted evidence is still available."
    finally:
        await manager.shutdown()
