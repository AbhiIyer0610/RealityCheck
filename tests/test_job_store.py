from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.jobs.models import JobStatus, StoredJob
from app.jobs.store import JobStore


@pytest.mark.asyncio
async def test_job_store_persists_job_and_marks_interrupted_running_job_failed(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "db" / "jobs.sqlite3")
    await store.initialize()

    artifact_path = tmp_path / "artifacts" / "example.txt"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("test", encoding="utf-8")

    job = StoredJob(
        job_id=uuid4(),
        artifact_id=uuid4(),
        filename="example.txt",
        media_type="text/plain",
        size_bytes=4,
        status=JobStatus.RUNNING,
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        artifact_path=artifact_path,
    )
    await store.create_job(job)

    loaded = await store.get_job(job.job_id)
    assert loaded is not None
    assert loaded.job_id == job.job_id
    assert loaded.status == JobStatus.RUNNING
    assert loaded.artifact_path == artifact_path

    recovered_count = await store.recover_interrupted_jobs()
    recovered = await store.get_job(job.job_id)
    assert recovered_count == 1
    assert recovered is not None
    assert recovered.status == JobStatus.FAILED
    assert recovered.completed_at is not None
    assert "server restarted" in (recovered.error_message or "").lower()


@pytest.mark.asyncio
async def test_job_store_reports_database_health(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    await store.initialize()
    assert await store.health_check() is True

@pytest.mark.asyncio
async def test_initialize_additively_migrates_existing_checkpoint_database(tmp_path: Path) -> None:
    import sqlite3

    database_path = tmp_path / "realitycheck.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """CREATE TABLE extraction_jobs (
            job_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
            media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, artifact_path TEXT NOT NULL,
            extraction_result_json TEXT, evidence_json TEXT NOT NULL DEFAULT '[]', error_message TEXT
        )"""
    )
    connection.commit()
    connection.close()

    store = JobStore(database_path)
    await store.initialize()
    connection = sqlite3.connect(database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(extraction_jobs)")}
    connection.close()
    assert {"claims_json", "findings_json", "analysis_status", "analysis_provider", "processing_stage", "progress_message"} <= columns
