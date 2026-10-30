from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.evidence.models import EvidenceObject
from app.ingestion.models import ExtractionResult
from app.jobs.models import JobStatus, StoredJob
from app.reasoning.models import AnalysisStatus, Claim, Finding
from app.reasoning.comparison import ComparisonResponse


class JobStore:
    """SQLite-backed job metadata and result store using only the stdlib."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_sync(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS extraction_jobs (
                    job_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    artifact_path TEXT NOT NULL,
                    extraction_result_json TEXT,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    claims_json TEXT NOT NULL DEFAULT '[]',
                    findings_json TEXT NOT NULL DEFAULT '[]',
                    analysis_status TEXT NOT NULL DEFAULT 'not_configured',
                    analysis_provider TEXT NOT NULL DEFAULT 'disabled',
                    analysis_error_message TEXT,
                    processing_stage TEXT NOT NULL DEFAULT 'queued',
                    progress_message TEXT NOT NULL DEFAULT 'Artifact accepted and waiting for a worker.',
                    error_message TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status_created "
                "ON extraction_jobs(status, created_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cross_document_comparisons (
                    comparison_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_cross_document_comparisons_created "
                "ON cross_document_comparisons(created_at)"
            )
            # Lightweight additive migration for databases created by earlier checkpoints.
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(extraction_jobs)").fetchall()
            }
            migrations = {
                "claims_json": "TEXT NOT NULL DEFAULT '[]'",
                "findings_json": "TEXT NOT NULL DEFAULT '[]'",
                "analysis_status": "TEXT NOT NULL DEFAULT 'not_configured'",
                "analysis_provider": "TEXT NOT NULL DEFAULT 'disabled'",
                "analysis_error_message": "TEXT",
                "processing_stage": "TEXT NOT NULL DEFAULT 'queued'",
                "progress_message": "TEXT NOT NULL DEFAULT 'Artifact accepted and waiting for a worker.'",
            }
            for column, declaration in migrations.items():
                if column not in existing_columns:
                    connection.execute(f"ALTER TABLE extraction_jobs ADD COLUMN {column} {declaration}")

    async def create_job(self, job: StoredJob) -> None:
        await asyncio.to_thread(self._create_job_sync, job)

    def _create_job_sync(self, job: StoredJob) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO extraction_jobs (
                    job_id, artifact_id, filename, media_type, size_bytes,
                    status, created_at, started_at, completed_at, artifact_path,
                    extraction_result_json, evidence_json, claims_json, findings_json,
                    analysis_status, analysis_provider, analysis_error_message, processing_stage, progress_message, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(job.job_id),
                    str(job.artifact_id),
                    job.filename,
                    job.media_type,
                    job.size_bytes,
                    job.status.value,
                    job.created_at.isoformat(),
                    _iso(job.started_at),
                    _iso(job.completed_at),
                    str(job.artifact_path),
                    _result_json(job.extraction_result),
                    _evidence_json(job.evidence),
                    _claims_json(job.claims),
                    _findings_json(job.findings),
                    job.analysis_status.value,
                    job.analysis_provider,
                    job.analysis_error_message,
                    job.processing_stage,
                    job.progress_message,
                    job.error_message,
                ),
            )

    async def get_job(self, job_id: UUID) -> StoredJob | None:
        return await asyncio.to_thread(self._get_job_sync, str(job_id))

    def _get_job_sync(self, job_id: str) -> StoredJob | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM extraction_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    async def list_jobs(self) -> list[StoredJob]:
        """Return persisted jobs newest first for the local analysis history."""
        return await asyncio.to_thread(self._list_jobs_sync)

    def _list_jobs_sync(self) -> list[StoredJob]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM extraction_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    async def list_comparisons(self) -> list[ComparisonResponse]:
        return await asyncio.to_thread(self._list_comparisons_sync)

    def _list_comparisons_sync(self) -> list[ComparisonResponse]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT result_json FROM cross_document_comparisons ORDER BY created_at DESC"
            ).fetchall()
        results: list[ComparisonResponse] = []
        for row in rows:
            try:
                results.append(ComparisonResponse.model_validate_json(row["result_json"]))
            except Exception:
                # A damaged history record should not prevent other entries from loading.
                continue
        return results

    async def list_pending_jobs(self) -> list[StoredJob]:
        return await asyncio.to_thread(self._list_pending_jobs_sync)

    def _list_pending_jobs_sync(self) -> list[StoredJob]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM extraction_jobs WHERE status = ? ORDER BY created_at",
                (JobStatus.PENDING.value,),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    async def mark_running(self, job_id: UUID) -> bool:
        return await asyncio.to_thread(self._mark_running_sync, str(job_id))

    def _mark_running_sync(self, job_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE extraction_jobs
                SET status = ?, started_at = ?, error_message = NULL,
                    processing_stage = ?, progress_message = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    _iso(datetime.now(timezone.utc)),
                    "extracting",
                    "Reading the artifact and extracting evidence.",
                    job_id,
                    JobStatus.PENDING.value,
                ),
            )
            return cursor.rowcount == 1

    async def complete_job(
        self,
        *,
        job_id: UUID,
        status: JobStatus,
        extraction_result: ExtractionResult,
        evidence: list[EvidenceObject],
        error_message: str | None = None,
    ) -> None:
        if not status.is_terminal:
            raise ValueError("A completed job must have a terminal status.")
        await asyncio.to_thread(
            self._complete_job_sync,
            str(job_id),
            status,
            extraction_result,
            evidence,
            error_message,
        )

    def _complete_job_sync(
        self,
        job_id: str,
        status: JobStatus,
        extraction_result: ExtractionResult,
        evidence: list[EvidenceObject],
        error_message: str | None,
    ) -> None:
        completed_at = _iso(datetime.now(timezone.utc))
        started_at = completed_at
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE extraction_jobs
                SET status = ?,
                    started_at = COALESCE(started_at, ?),
                    completed_at = ?,
                    extraction_result_json = ?,
                    evidence_json = ?,
                    processing_stage = CASE WHEN ? = 'failed' THEN 'failed' ELSE processing_stage END,
                    progress_message = CASE WHEN ? = 'failed' THEN ? ELSE progress_message END,
                    error_message = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    status.value,
                    started_at,
                    completed_at,
                    extraction_result.model_dump_json(),
                    _evidence_json(evidence),
                    status.value,
                    status.value,
                    error_message or "Processing failed.",
                    error_message,
                    job_id,
                    JobStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Job {job_id} was not in running state when completion was saved."
                )

    async def save_extraction_stage(
        self, job_id: UUID, extraction_result: ExtractionResult, evidence: list[EvidenceObject],
        *, processing_stage: str, progress_message: str,
    ) -> None:
        await asyncio.to_thread(
            self._save_extraction_stage_sync, str(job_id), extraction_result, evidence,
            processing_stage, progress_message,
        )

    def _save_extraction_stage_sync(
        self, job_id: str, extraction_result: ExtractionResult, evidence: list[EvidenceObject],
        processing_stage: str, progress_message: str,
    ) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE extraction_jobs SET extraction_result_json = ?, evidence_json = ?,
                   processing_stage = ?, progress_message = ?
                   WHERE job_id = ? AND status = ?""",
                (_result_json(extraction_result), _evidence_json(evidence), processing_stage,
                 progress_message, job_id, JobStatus.RUNNING.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Job {job_id} was not running when extraction evidence was saved.")

    async def update_analysis_progress(
        self, job_id: UUID, *, processing_stage: str, progress_message: str,
        analysis_status: AnalysisStatus | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._update_analysis_progress_sync, str(job_id), processing_stage,
            progress_message, analysis_status,
        )

    def _update_analysis_progress_sync(
        self, job_id: str, processing_stage: str, progress_message: str,
        analysis_status: AnalysisStatus | None,
    ) -> None:
        with self._connection() as connection:
            if analysis_status is None:
                connection.execute(
                    "UPDATE extraction_jobs SET processing_stage = ?, progress_message = ? WHERE job_id = ? AND status = ?",
                    (processing_stage, progress_message, job_id, JobStatus.RUNNING.value),
                )
            else:
                connection.execute(
                    "UPDATE extraction_jobs SET processing_stage = ?, progress_message = ?, analysis_status = ? WHERE job_id = ? AND status = ?",
                    (processing_stage, progress_message, analysis_status.value, job_id, JobStatus.RUNNING.value),
                )

    async def save_claims(self, job_id: UUID, claims: list[Claim]) -> None:
        await asyncio.to_thread(self._save_claims_sync, str(job_id), claims)

    def _save_claims_sync(self, job_id: str, claims: list[Claim]) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE extraction_jobs SET claims_json = ? WHERE job_id = ? AND status = ?",
                (_claims_json(claims), job_id, JobStatus.RUNNING.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Could not persist claims for running job {job_id}.")

    async def save_findings(self, job_id: UUID, findings: list[Finding]) -> None:
        await asyncio.to_thread(self._save_findings_sync, str(job_id), findings)

    def _save_findings_sync(self, job_id: str, findings: list[Finding]) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE extraction_jobs SET findings_json = ? WHERE job_id = ? AND status = ?",
                (_findings_json(findings), job_id, JobStatus.RUNNING.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Could not persist findings for running job {job_id}.")

    async def finish_analysis(
        self, job_id: UUID, *, status: AnalysisStatus, error_message: str | None = None,
        progress_message: str,
    ) -> None:
        await asyncio.to_thread(
            self._finish_analysis_sync, str(job_id), status, error_message, progress_message
        )

    def _finish_analysis_sync(
        self, job_id: str, status: AnalysisStatus, error_message: str | None,
        progress_message: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """UPDATE extraction_jobs SET analysis_status = ?, analysis_error_message = ?,
                   processing_stage = ?, progress_message = ? WHERE job_id = ? AND status = ?""",
                (status.value, error_message, "analysis_failed" if status == AnalysisStatus.FAILED else "complete",
                 progress_message, job_id, JobStatus.RUNNING.value),
            )

    async def list_referenced_artifact_paths(self) -> set[Path]:
        return await asyncio.to_thread(self._list_referenced_artifact_paths_sync)

    def _list_referenced_artifact_paths_sync(self) -> set[Path]:
        with self._connection() as connection:
            rows = connection.execute("SELECT artifact_path FROM extraction_jobs").fetchall()
        return {Path(row["artifact_path"]).resolve() for row in rows}

    async def fail_unstarted_job(self, job_id: UUID, message: str) -> None:
        await asyncio.to_thread(self._fail_unstarted_job_sync, str(job_id), message)

    def _fail_unstarted_job_sync(self, job_id: str, message: str) -> None:
        now = _iso(datetime.now(timezone.utc))
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE extraction_jobs
                SET status = ?, completed_at = ?, processing_stage = 'failed',
                    progress_message = ?, error_message = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    JobStatus.FAILED.value,
                    now,
                    message,
                    message,
                    job_id,
                    JobStatus.PENDING.value,
                ),
            )

    async def recover_interrupted_jobs(self) -> int:
        return await asyncio.to_thread(self._recover_interrupted_jobs_sync)

    def _recover_interrupted_jobs_sync(self) -> int:
        completed_at = _iso(datetime.now(timezone.utc))
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE extraction_jobs
                SET status = ?, completed_at = ?, processing_stage = 'failed',
                    analysis_status = CASE WHEN analysis_status = 'running' THEN 'failed' ELSE analysis_status END,
                    analysis_error_message = CASE WHEN analysis_status = 'running' THEN 'The server restarted during AI analysis.' ELSE analysis_error_message END,
                    progress_message = ?, error_message = ?
                WHERE status = ?
                """,
                (
                    JobStatus.FAILED.value,
                    completed_at,
                    "The server restarted while this job was running. Please upload the artifact again.",
                    "The server restarted while this job was running. Please upload the artifact again.",
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount

    async def delete_completed_job(self, job_id: UUID) -> bool:
        """Delete a terminal job from history; active work cannot be deleted here."""
        return await asyncio.to_thread(self._delete_completed_job_sync, str(job_id))

    def _delete_completed_job_sync(self, job_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM extraction_jobs WHERE job_id = ? AND status IN (?, ?, ?)",
                (job_id, JobStatus.SUCCEEDED.value, JobStatus.PARTIAL.value, JobStatus.FAILED.value),
            )
        return cursor.rowcount == 1

    async def delete_comparison(self, comparison_id: UUID) -> bool:
        return await asyncio.to_thread(self._delete_comparison_sync, str(comparison_id))

    def _delete_comparison_sync(self, comparison_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM cross_document_comparisons WHERE comparison_id = ?", (comparison_id,)
            )
        return cursor.rowcount == 1

    async def delete_job(self, job_id: UUID) -> None:
        await asyncio.to_thread(self._delete_job_sync, str(job_id))

    def _delete_job_sync(self, job_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM extraction_jobs WHERE job_id = ? AND status = ?",
                (job_id, JobStatus.PENDING.value),
            )

    async def list_expired_terminal_jobs(self, cutoff: datetime) -> list[StoredJob]:
        """Return terminal jobs completed before cutoff; active jobs are never selected."""
        return await asyncio.to_thread(self._list_expired_terminal_jobs_sync, _iso(cutoff))

    def _list_expired_terminal_jobs_sync(self, cutoff_iso: str) -> list[StoredJob]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM extraction_jobs
                WHERE status IN (?, ?, ?) AND completed_at IS NOT NULL AND completed_at < ?
                ORDER BY completed_at
                """,
                (
                    JobStatus.SUCCEEDED.value,
                    JobStatus.PARTIAL.value,
                    JobStatus.FAILED.value,
                    cutoff_iso,
                ),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    async def delete_expired_job(self, job_id: UUID, cutoff: datetime) -> bool:
        return await asyncio.to_thread(
            self._delete_expired_job_sync, str(job_id), _iso(cutoff)
        )

    def _delete_expired_job_sync(self, job_id: str, cutoff_iso: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM extraction_jobs
                WHERE job_id = ? AND status IN (?, ?, ?)
                    AND completed_at IS NOT NULL AND completed_at < ?
                """,
                (
                    job_id,
                    JobStatus.SUCCEEDED.value,
                    JobStatus.PARTIAL.value,
                    JobStatus.FAILED.value,
                    cutoff_iso,
                ),
            )
            return cursor.rowcount == 1

    async def save_comparison(self, comparison: ComparisonResponse) -> None:
        await asyncio.to_thread(self._save_comparison_sync, comparison)

    def _save_comparison_sync(self, comparison: ComparisonResponse) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO cross_document_comparisons (comparison_id, created_at, result_json) VALUES (?, ?, ?)",
                (str(comparison.comparison_id), comparison.created_at.isoformat(), comparison.model_dump_json()),
            )

    async def get_comparison(self, comparison_id: UUID) -> ComparisonResponse | None:
        return await asyncio.to_thread(self._get_comparison_sync, str(comparison_id))

    def _get_comparison_sync(self, comparison_id: str) -> ComparisonResponse | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM cross_document_comparisons WHERE comparison_id = ?",
                (comparison_id,),
            ).fetchone()
        return ComparisonResponse.model_validate_json(row["result_json"]) if row else None

    async def delete_expired_comparisons(self, cutoff: datetime) -> int:
        return await asyncio.to_thread(self._delete_expired_comparisons_sync, cutoff.isoformat())

    def _delete_expired_comparisons_sync(self, cutoff_iso: str) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM cross_document_comparisons WHERE created_at < ?", (cutoff_iso,)
            )
            return cursor.rowcount

    async def delete_comparisons_for_job(self, job_id: UUID) -> int:
        return await asyncio.to_thread(self._delete_comparisons_for_job_sync, str(job_id))

    def _delete_comparisons_for_job_sync(self, job_id: str) -> int:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT comparison_id, result_json FROM cross_document_comparisons"
            ).fetchall()
            expired_ids: list[str] = []
            for row in rows:
                try:
                    comparison = ComparisonResponse.model_validate_json(row["result_json"])
                except Exception:
                    # A malformed record should not prevent retention from cleaning other data.
                    continue
                if any(str(document.job_id) == job_id for document in comparison.documents):
                    expired_ids.append(row["comparison_id"])
            if not expired_ids:
                return 0
            connection.executemany(
                "DELETE FROM cross_document_comparisons WHERE comparison_id = ?",
                [(item,) for item in expired_ids],
            )
            return len(expired_ids)

    async def health_check(self) -> bool:
        return await asyncio.to_thread(self._health_check_sync)

    def _health_check_sync(self) -> bool:
        try:
            with self._connection() as connection:
                row = connection.execute("SELECT 1").fetchone()
            return row is not None and row[0] == 1
        except sqlite3.Error:
            return False


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _result_json(result: ExtractionResult | None) -> str | None:
    return result.model_dump_json() if result is not None else None


def _evidence_json(evidence: list[EvidenceObject]) -> str:
    return json.dumps(
        [item.model_dump(mode="json") for item in evidence],
        ensure_ascii=False,
    )


def _claims_json(claims: list[Claim]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in claims], ensure_ascii=False)


def _findings_json(findings: list[Finding]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in findings], ensure_ascii=False)


def _row_to_job(row: sqlite3.Row) -> StoredJob:
    result_json = row["extraction_result_json"]
    evidence_data: list[dict[str, Any]] = json.loads(row["evidence_json"] or "[]")
    return StoredJob(
        job_id=row["job_id"],
        artifact_id=row["artifact_id"],
        filename=row["filename"],
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        artifact_path=Path(row["artifact_path"]),
        extraction_result=(
            ExtractionResult.model_validate_json(result_json)
            if result_json
            else None
        ),
        evidence=[EvidenceObject.model_validate(item) for item in evidence_data],
        claims=[Claim.model_validate(item) for item in json.loads(row["claims_json"] or "[]")],
        findings=[Finding.model_validate(item) for item in json.loads(row["findings_json"] or "[]")],
        analysis_status=row["analysis_status"],
        analysis_provider=row["analysis_provider"] if "analysis_provider" in row.keys() else "disabled",
        analysis_error_message=row["analysis_error_message"],
        processing_stage=row["processing_stage"],
        progress_message=row["progress_message"],
        error_message=row["error_message"],
    )
