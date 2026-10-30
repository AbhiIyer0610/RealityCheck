from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.jobs.models import JobStatus, StoredJob
from app.jobs.store import JobStore


@pytest.mark.asyncio
async def test_retention_lists_and_deletes_only_expired_terminal_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    await store.initialize()
    old = datetime.now(timezone.utc) - timedelta(days=40)
    recent = datetime.now(timezone.utc) - timedelta(days=2)
    expired = StoredJob(
        job_id=uuid4(), artifact_id=uuid4(), filename="old.txt", media_type="text/plain",
        size_bytes=3, status=JobStatus.SUCCEEDED, created_at=old, started_at=old,
        completed_at=old, artifact_path=tmp_path / "old.txt",
    )
    recent_job = StoredJob(
        job_id=uuid4(), artifact_id=uuid4(), filename="recent.txt", media_type="text/plain",
        size_bytes=3, status=JobStatus.SUCCEEDED, created_at=recent, started_at=recent,
        completed_at=recent, artifact_path=tmp_path / "recent.txt",
    )
    pending = StoredJob(
        job_id=uuid4(), artifact_id=uuid4(), filename="pending.txt", media_type="text/plain",
        size_bytes=3, status=JobStatus.PENDING, created_at=old,
        artifact_path=tmp_path / "pending.txt",
    )
    for job in (expired, recent_job, pending):
        await store.create_job(job)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    expired_jobs = await store.list_expired_terminal_jobs(cutoff)
    assert [job.job_id for job in expired_jobs] == [expired.job_id]
    assert await store.delete_expired_job(expired.job_id, cutoff) is True
    assert await store.get_job(expired.job_id) is None
    assert await store.get_job(recent_job.job_id) is not None
    assert await store.get_job(pending.job_id) is not None


@pytest.mark.asyncio
async def test_retention_does_not_delete_terminal_job_before_cutoff(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    await store.initialize()
    now = datetime.now(timezone.utc)
    job = StoredJob(
        job_id=uuid4(), artifact_id=uuid4(), filename="recent.txt", media_type="text/plain",
        size_bytes=3, status=JobStatus.FAILED, created_at=now, started_at=now,
        completed_at=now, artifact_path=tmp_path / "recent.txt",
    )
    await store.create_job(job)
    cutoff = now - timedelta(days=30)
    assert await store.delete_expired_job(job.job_id, cutoff) is False
    assert await store.get_job(job.job_id) is not None


@pytest.mark.asyncio
async def test_manager_retention_removes_artifact_and_expired_job(tmp_path: Path) -> None:
    from app.core.config import Settings
    from app.ingestion.text_extractor import TextExtractor
    from app.jobs.manager import JobManager

    settings = Settings(
        _env_file=None, data_dir=tmp_path, max_concurrent_extractions=1,
        job_retention_days=30, job_cleanup_interval_seconds=3600,
    )
    manager = JobManager(settings, extractors={"text/plain": TextExtractor()})
    await manager.start()
    try:
        old = datetime.now(timezone.utc) - timedelta(days=40)
        artifact_path = tmp_path / "artifacts" / "expired.txt"
        artifact_path.write_text("old source", encoding="utf-8")
        job = StoredJob(
            job_id=uuid4(), artifact_id=uuid4(), filename="expired.txt",
            media_type="text/plain", size_bytes=10, status=JobStatus.SUCCEEDED,
            created_at=old, started_at=old, completed_at=old, artifact_path=artifact_path,
        )
        await manager._store.create_job(job)
        await manager._cleanup_expired_jobs()
        assert await manager.get_job(job.job_id) is None
        assert not artifact_path.exists()
    finally:
        await manager.shutdown()
