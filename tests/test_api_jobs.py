from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.jobs.manager import JobManager
from app.main import create_app
from app.ingestion.text_extractor import TextExtractor


def _build_test_app(data_dir: Path, *, max_upload_size_mb: int = 1):
    test_settings = Settings(
        _env_file=None,
        data_dir=data_dir,
        max_upload_size_mb=max_upload_size_mb,
        max_concurrent_extractions=1,
        max_pending_extraction_jobs=2,
        frontend_origin="http://localhost:5173",
    )

    def manager_factory(settings: Settings) -> JobManager:
        # Keep API tests fast and deterministic; PDF process isolation is covered
        # by the existing PDF extractor/runtime tests.
        return JobManager(settings, extractors={"text/plain": TextExtractor()})

    return create_app(
        settings_override=test_settings,
        manager_factory=manager_factory,
    )


def _wait_for_terminal_status(client: TestClient, job_id: str) -> dict:
    deadline = time.monotonic() + 5
    latest: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] in {"succeeded", "partial", "failed"}:
            return latest
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish before timeout; last response: {latest}")


def test_upload_text_job_and_retrieve_evidence(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    content = b"RealityCheck evidence is persisted with its provenance."

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/ready").json() == {"status": "ready"}

        upload = client.post(
            "/api/v1/artifacts",
            files={"file": ("notes.txt", content, "text/plain")},
        )
        assert upload.status_code == 202, upload.text
        submitted = upload.json()
        assert submitted["status"] == "pending"
        assert submitted["filename"] == "notes.txt"
        assert submitted["size_bytes"] == len(content)
        job_id = submitted["job_id"]

        completed = _wait_for_terminal_status(client, job_id)
        assert completed["status"] == "succeeded"
        assert completed["extraction_status"] == "success"
        assert completed["element_count"] == 1
        assert completed["evidence_count"] == 1
        assert completed["diagnostics"] == []

        evidence_response = client.get(f"/api/v1/jobs/{job_id}/evidence")
        assert evidence_response.status_code == 200
        evidence_payload = evidence_response.json()
        assert evidence_payload["count"] == 1
        evidence = evidence_payload["items"][0]
        assert evidence["content"] == content.decode("utf-8")
        assert evidence["provenance"]["source_name"] == "notes.txt"
        assert evidence["provenance"]["artifact_type"] == "text"
        assert evidence["provenance"]["extraction_method"] == "text-extractor"
        analysis_response = client.get(f"/api/v1/jobs/{job_id}/analysis")
        assert analysis_response.status_code == 200
        analysis_payload = analysis_response.json()
        assert analysis_payload["analysis_status"] == "not_configured"
        assert analysis_payload["claims"] == []
        assert analysis_payload["findings"] == []


def test_offline_provider_returns_clearly_labelled_source_linked_analysis(tmp_path: Path) -> None:
    from app.reasoning.offline_demo import OfflineDemoAnalyzer

    test_settings = Settings(
        _env_file=None, data_dir=tmp_path, max_upload_size_mb=1,
        max_concurrent_extractions=1, max_pending_extraction_jobs=2,
        analysis_provider="offline", frontend_origin="http://localhost:5173",
    )

    def manager_factory(settings: Settings) -> JobManager:
        return JobManager(
            settings, extractors={"text/plain": TextExtractor()},
            claim_analyzer=OfflineDemoAnalyzer(),
        )

    app = create_app(settings_override=test_settings, manager_factory=manager_factory)
    with TestClient(app) as client:
        upload = client.post(
            "/api/v1/artifacts",
            files={"file": ("requirement.txt", b"The service must accept PDF files.", "text/plain")},
        )
        assert upload.status_code == 202, upload.text
        job_id = upload.json()["job_id"]
        completed = _wait_for_terminal_status(client, job_id)
        assert completed["analysis_provider"] == "offline_demo"
        analysis = client.get(f"/api/v1/jobs/{job_id}/analysis").json()
        assert analysis["analysis_provider"] == "offline_demo"
        assert analysis["analysis_status"] == "succeeded"
        assert analysis["claims"]
        assert analysis["findings"]
        assert all(item["status"] == "uncertain" for item in analysis["findings"])
        assert all(item["evidence_ids"] for item in analysis["claims"])


def test_upload_rejects_unsupported_media_type(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/artifacts",
            files={"file": ("image.png", b"not-an-image", "image/png")},
        )
    assert response.status_code == 415


def test_upload_rejects_invalid_pdf_signature(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/artifacts",
            files={"file": ("fake.pdf", b"this is not a pdf", "application/pdf")},
        )
    assert response.status_code == 422
    assert "PDF header" in response.json()["detail"]


def test_upload_rejects_invalid_utf8_text(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/artifacts",
            files={"file": ("bad.txt", b"\xff\xfe", "text/plain")},
        )
    assert response.status_code == 422
    assert "UTF-8" in response.json()["detail"]


def test_upload_enforces_configured_size_limit(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path, max_upload_size_mb=1)
    oversized_content = b"x" * (1024 * 1024 + 1)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/artifacts",
            files={"file": ("large.txt", oversized_content, "text/plain")},
        )
    assert response.status_code == 413


def test_unknown_job_returns_404(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/jobs/{uuid4()}")
    assert response.status_code == 404


def test_filename_path_components_are_not_exposed_or_used_as_storage_paths(
    tmp_path: Path,
) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/artifacts",
            files={"file": ("../../private.txt", b"safe text", "text/plain")},
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["filename"] == "private.txt"
        job_id = payload["job_id"]
        _wait_for_terminal_status(client, job_id)

    stored_files = list((tmp_path / "artifacts").glob("*"))
    assert len(stored_files) == 1
    assert stored_files[0].name == f"{job_id}.txt"


def test_history_lists_uploaded_document_after_processing(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        upload = client.post(
            "/api/v1/artifacts",
            files={"file": ("history.txt", b"A historical source claim.", "text/plain")},
        )
        assert upload.status_code == 202, upload.text
        job_id = upload.json()["job_id"]
        _wait_for_terminal_status(client, job_id)
        history = client.get("/api/v1/history")
        assert history.status_code == 200, history.text
        payload = history.json()
        entry = next(item for item in payload["items"] if item["job_id"] == job_id)
        assert entry["kind"] == "document"
        assert entry["title"] == "history.txt"
        assert entry["document_count"] == 1
        # A single upload creates exactly one top-level history entry.
        assert len(payload["items"]) == 1


def test_delete_history_item_removes_completed_job_and_artifact(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        upload = client.post(
            "/api/v1/artifacts",
            files={"file": ("remove-me.txt", b"Delete this source after testing.", "text/plain")},
        )
        assert upload.status_code == 202, upload.text
        job_id = upload.json()["job_id"]
        _wait_for_terminal_status(client, job_id)
        deleted = client.delete(f"/api/v1/jobs/{job_id}/history")
        assert deleted.status_code == 204, deleted.text
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
        history = client.get("/api/v1/history").json()
        assert all(item["id"] != job_id for item in history["items"])


def test_delete_history_rejects_unknown_job(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.delete(f"/api/v1/jobs/{uuid4()}/history")
        assert response.status_code == 404
