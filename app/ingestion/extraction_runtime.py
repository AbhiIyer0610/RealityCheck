from __future__ import annotations

import asyncio
from uuid import UUID
import multiprocessing
from typing import Any, Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from app.ingestion.docling_worker import convert_pdf_payload
from app.ingestion.models import ExtractionResult


class ExtractionWorkerError(RuntimeError):
    """Raised when the extraction worker process becomes unavailable."""


class DoclingExtractionRuntime:
    def __init__(
        self,
        max_concurrent_extractions: int,
        worker: Callable[..., dict[str, Any]] = convert_pdf_payload,
    ) -> None:
        if max_concurrent_extractions < 1:
            raise ValueError(
                "max_concurrent_extractions must be at least 1."
            )

        self._max_workers = max_concurrent_extractions
        self._worker = worker
        self._semaphore = asyncio.Semaphore(max_concurrent_extractions)
        self._replacement_lock = asyncio.Lock()
        self._closed = False

        self._executor = self._create_executor()

    def _create_executor(self) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=multiprocessing.get_context("spawn"),
        )

    async def extract_pdf(
        self,
        *,
        filename: str,
        pdf_bytes: bytes,
        artifact_id: UUID,
        extractor_version: str,
    ) -> ExtractionResult:
        async with self._semaphore:
            if self._closed:
                raise RuntimeError("Extraction runtime is shut down.")

            executor = self._executor
            loop = asyncio.get_running_loop()

            try:
                payload = await loop.run_in_executor(
                    executor,
                    self._worker,
                    filename,
                    pdf_bytes,
                    str(artifact_id),
                    extractor_version,
                )
            except BrokenProcessPool as exc:
                await self._replace_broken_executor(executor)
                raise ExtractionWorkerError(
                    "The PDF extraction worker process terminated "
                    "unexpectedly. The worker pool has been reset."
                ) from exc

            return ExtractionResult.model_validate(payload)

    async def _replace_broken_executor(
        self,
        failed_executor: ProcessPoolExecutor,
    ) -> None:
        async with self._replacement_lock:
            if self._closed or self._executor is not failed_executor:
                return

            self._executor = self._create_executor()

            # The pool is already broken. Do not block the event loop waiting for its shutdown.
            failed_executor.shutdown(
                wait=False,
                cancel_futures=True,
            )

    async def shutdown(self) -> None:
        if self._closed:
            return

        self._closed = True
        executor = self._executor

        # Executor shutdown may wait for active work, so do not execute it synchronously on the event loop.
        await asyncio.to_thread(
            executor.shutdown,
            wait=True,
            cancel_futures=True,
        )