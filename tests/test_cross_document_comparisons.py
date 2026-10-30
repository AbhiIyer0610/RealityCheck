from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.ingestion.text_extractor import TextExtractor
from app.jobs.manager import JobManager
from app.main import create_app
from app.reasoning.offline_demo import OfflineDemoAnalyzer


def _build_app(data_dir: Path):
    settings = Settings(
        _env_file=None,
        data_dir=data_dir,
        max_upload_size_mb=1,
        max_concurrent_extractions=1,
        max_pending_extraction_jobs=5,
        analysis_provider="offline",
        frontend_origin="http://localhost:5173",
    )

    def manager_factory(config: Settings) -> JobManager:
        return JobManager(
            config,
            extractors={"text/plain": TextExtractor()},
            claim_analyzer=OfflineDemoAnalyzer(),
        )

    return create_app(settings_override=settings, manager_factory=manager_factory)


def _upload_and_wait(client: TestClient, filename: str, content: str) -> str:
    response = client.post(
        "/api/v1/artifacts",
        files={"file": (filename, content.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "partial", "failed"}:
            assert job["status"] == "succeeded", job
            assert job["analysis_status"] == "succeeded", job
            return job_id
        time.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not finish in time")


def test_cross_document_comparison_flags_numeric_upload_limit_candidate_and_persists(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        requirement_id = _upload_and_wait(
            client, "requirements.txt", "Requirement R-002: The maximum upload size is 80 MB by default."
        )
        implementation_id = _upload_and_wait(
            client, "implementation.txt", "The file exceeds the 50 MB upload limit."
        )

        response = client.post(
            "/api/v1/comparisons", json={"job_ids": [requirement_id, implementation_id]}
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["mode"] == "offline_heuristic"
        assert len(result["documents"]) == 2
        assert result["claims"]
        assert len(result["findings"]) == 1
        finding = result["findings"][0]
        assert finding["status"] == "uncertain"
        assert "80 mb" in finding["explanation"].lower()
        assert "50 mb" in finding["explanation"].lower()
        assert len(finding["evidence_ids"]) == 2
        assert len(finding["claim_ids"]) == 2

        saved = client.get(f"/api/v1/comparisons/{result['comparison_id']}")
        assert saved.status_code == 200
        assert saved.json() == result

        # A comparison is the single user-facing history record. Source jobs stay
        # persisted for evidence/provenance but are not duplicated in top-level history.
        history_response = client.get("/api/v1/history")
        assert history_response.status_code == 200, history_response.text
        history = history_response.json()
        comparison_entry = next(
            item for item in history["items"] if item["comparison_id"] == result["comparison_id"]
        )
        assert set(comparison_entry["source_job_ids"]) == {requirement_id, implementation_id}
        assert all(item.get("job_id") not in {requirement_id, implementation_id} for item in history["items"])
        # A successful multi-document comparison creates one top-level history entry,
        # not one entry per uploaded source document plus a comparison entry.
        assert len(history["items"]) == 1

        # Deleting the comparison preserves source jobs; since they are no longer
        # grouped by a saved comparison, they become standalone history entries again.
        deleted = client.delete(f"/api/v1/comparisons/{result['comparison_id']}")
        assert deleted.status_code == 204, deleted.text
        ungrouped_history = client.get("/api/v1/history").json()
        assert {item.get("job_id") for item in ungrouped_history["items"] if item["kind"] == "document"} >= {requirement_id, implementation_id}


def test_comparison_rejects_duplicate_job_ids(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        job_id = _upload_and_wait(client, "one.txt", "A small source statement about the system.")
        response = client.post("/api/v1/comparisons", json={"job_ids": [job_id, job_id]})
        assert response.status_code == 422


def test_comparison_requires_completed_analysis(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/comparisons", json={"job_ids": ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]})
        assert response.status_code == 404
