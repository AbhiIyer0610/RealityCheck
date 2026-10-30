import os
import time
import pytest
import asyncio
from uuid import uuid4

from app.ingestion.extraction_runtime import DoclingExtractionRuntime
from app.ingestion.models import ExtractionStatus


def slow_test_worker(
    filename: str,
    pdf_bytes: bytes,
    artifact_id: str,
    extractor_version: str,
) -> dict:
    """Importable worker used to test the process boundary."""
    time.sleep(0.2)

    return {
        "artifact_id": artifact_id,
        "status": "success",
        "elements": [],
        "diagnostics": [],
        "extractor_name": "test-worker",
        "extractor_version": extractor_version,
        "metadata": {
            "worker_pid": os.getpid(),
            "filename": filename,
            "input_size": len(pdf_bytes),
        },
    }


@pytest.mark.asyncio
async def test_runtime_executes_work_in_another_process() -> None:
    runtime = DoclingExtractionRuntime(
        max_concurrent_extractions=1,
        worker=slow_test_worker,
    )

    try:
        result = await runtime.extract_pdf(
            filename="test.pdf",
            pdf_bytes=b"test",
            artifact_id=uuid4(),
            extractor_version="test",
        )

        assert result.status == ExtractionStatus.SUCCESS
        assert result.metadata["worker_pid"] != os.getpid()
        assert result.metadata["filename"] == "test.pdf"
        assert result.metadata["input_size"] == 4
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_keeps_event_loop_responsive() -> None:
    runtime = DoclingExtractionRuntime(
        max_concurrent_extractions=1,
        worker=slow_test_worker,
    )

    try:
        artifact_id = uuid4()
        heartbeat_times: list[float] = []
        start = time.perf_counter()

        async def heartbeat() -> None:
            await asyncio.sleep(0.02)
            heartbeat_times.append(time.perf_counter())

        result, _ = await asyncio.gather(
            runtime.extract_pdf(
                filename="test.pdf",
                pdf_bytes=b"test",
                artifact_id=artifact_id,
                extractor_version="test",
            ),
            heartbeat(),
        )

        assert result.status == ExtractionStatus.SUCCESS
        assert heartbeat_times
        assert heartbeat_times[0] - start < 0.15
    finally:
        await runtime.shutdown()


def test_runtime_rejects_invalid_worker_count() -> None:
    with pytest.raises(
        ValueError,
        match="max_concurrent_extractions must be at least 1",
    ):
        DoclingExtractionRuntime(max_concurrent_extractions=0)