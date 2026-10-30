from uuid import UUID
from pathlib import PurePosixPath

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.core.config import Settings
from app.api.schemas import (
    AnalysisResponse, ComparisonApiResponse, CompareJobsRequest, EvidenceListResponse,
    HistoryItem, HistoryResponse, JobResponse, TavilySearchRequest, TavilySearchResponse, TavilySearchResult,
)
from app.jobs.manager import (
    ComparisonAnalysisFailed, ComparisonJobNotFound, ComparisonNotConfigured,
    ComparisonNotReady, JobManager, JobManagerNotStarted, JobQueueFull,
)

router = APIRouter()


@router.post(
    "/research/tavily/search",
    response_model=TavilySearchResponse,
    summary="Search public sources for optional external verification",
)
async def search_tavily(request: Request, payload: TavilySearchRequest) -> TavilySearchResponse:
    """Search public sources on explicit user request; never sends uploaded document text."""
    app_settings: Settings = request.app.state.settings
    api_key = app_settings.tavily_api_key
    if api_key is None or not api_key.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tavily is not configured. Set TAVILY_API_KEY in .env and restart the backend.",
        )

    body: dict[str, object] = {
        "query": payload.query,
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False,
    }
    if payload.include_domains:
        body["include_domains"] = payload.include_domains

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            result_data = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Tavily search timed out. Try again.") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Tavily rejected the configured API key.") from exc
        if exc.response.status_code == 429:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tavily rate limit reached. Try again later.") from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Tavily search failed with HTTP {exc.response.status_code}.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not reach Tavily or parse its response.") from exc

    results = []
    for item in result_data.get("results", [])[:5]:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        results.append(TavilySearchResult(
            title=str(item.get("title") or item["url"])[:300],
            url=str(item["url"])[:2000],
            content=str(item.get("content") or "")[:3000],
            score=float(item["score"]) if isinstance(item.get("score"), (int, float)) else None,
        ))
    return TavilySearchResponse(query=payload.query, results=results)


@router.get("/history", response_model=HistoryResponse, summary="List saved document analyses and comparisons")
async def list_analysis_history(request: Request) -> HistoryResponse:
    manager: JobManager = request.app.state.job_manager
    jobs = await manager.list_history_jobs()
    comparisons = await manager.list_history_comparisons()
    # A cross-document comparison is the user-facing analysis record. Its source
    # jobs remain persisted for status/provenance retrieval but are not duplicated
    # as separate top-level history entries while a saved comparison references them.
    comparison_source_job_ids = {
        document.job_id for comparison in comparisons for document in comparison.documents
    }
    items: list[HistoryItem] = []
    for job in jobs:
        if job.job_id in comparison_source_job_ids:
            continue
        items.append(HistoryItem(
            id=job.job_id, job_id=job.job_id, kind="document", title=job.filename,
            created_at=job.created_at, status=(job.analysis_status.value if job.status.is_terminal else job.status.value),
            document_count=1, claim_count=len(job.claims), finding_count=len(job.findings),
            document_names=[job.filename],
        ))
    for comparison in comparisons:
        items.append(HistoryItem(
            id=comparison.comparison_id, comparison_id=comparison.comparison_id, kind="comparison",
            title=" vs ".join(document.filename for document in comparison.documents),
            created_at=comparison.created_at, status="completed", document_count=len(comparison.documents),
            claim_count=len(comparison.claims), finding_count=len(comparison.findings),
            document_names=[document.filename for document in comparison.documents],
            source_job_ids=[document.job_id for document in comparison.documents],
        ))
    items.sort(key=lambda item: item.created_at, reverse=True)
    return HistoryResponse(items=items[:100], total=len(items))


@router.delete("/jobs/{job_id}/history", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a completed document analysis")
async def delete_document_history(request: Request, job_id: UUID) -> None:
    manager: JobManager = request.app.state.job_manager
    try:
        deleted = await manager.delete_history_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Completed document analysis not found.")


@router.delete("/comparisons/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a saved comparison")
async def delete_comparison_history(request: Request, comparison_id: UUID) -> None:
    manager: JobManager = request.app.state.job_manager
    deleted = await manager.delete_history_comparison(comparison_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found or expired.")


@router.post(
    "/artifacts",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload an artifact and queue extraction",
)
async def create_artifact_job(
    request: Request,
    file: UploadFile = File(...),
) -> JobResponse:
    app_settings: Settings = request.app.state.settings
    manager: JobManager = request.app.state.job_manager

    try:
        async with request.app.state.upload_semaphore:
            filename = _safe_filename(file.filename)
            media_type = _supported_media_type(file.content_type, filename)
            max_bytes = app_settings.max_upload_size_mb * 1024 * 1024
            content = await _read_limited_upload(file, max_bytes)
            _validate_content(media_type, content)

            job = await manager.submit(
                filename=filename,
                media_type=media_type,
                content=content,
            )
    except JobQueueFull as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": "5"},
        ) from exc
    except JobManagerNotStarted as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The extraction service is not ready. Retry shortly.",
            headers={"Retry-After": "5"},
        ) from exc
    finally:
        await file.close()

    return JobResponse.from_stored_job(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get extraction job status and diagnostics",
)
async def get_job(request: Request, job_id: UUID) -> JobResponse:
    manager: JobManager = request.app.state.job_manager
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobResponse.from_stored_job(job)


@router.get(
    "/jobs/{job_id}/analysis",
    response_model=AnalysisResponse,
    summary="Get incrementally available claims and reconciliation findings",
)
async def get_job_analysis(request: Request, job_id: UUID) -> AnalysisResponse:
    manager: JobManager = request.app.state.job_manager
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return AnalysisResponse(
        job_id=job.job_id,
        status=job.status,
        analysis_status=job.analysis_status,
        analysis_provider=job.analysis_provider,
        processing_stage=job.processing_stage,
        progress_message=job.progress_message,
        error_message=job.analysis_error_message,
        claims=job.claims,
        findings=job.findings,
    )


@router.post(
    "/comparisons",
    response_model=ComparisonApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Compare claims across completed source documents",
)
async def create_cross_document_comparison(
    request: Request, payload: CompareJobsRequest
) -> ComparisonApiResponse:
    manager: JobManager = request.app.state.job_manager
    try:
        return await manager.compare_jobs(payload.job_ids)
    except ComparisonJobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ComparisonNotReady as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ComparisonNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ComparisonAnalysisFailed as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except JobManagerNotStarted as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The analysis service is not ready.") from exc


@router.get(
    "/comparisons/{comparison_id}",
    response_model=ComparisonApiResponse,
    summary="Retrieve a saved cross-document comparison",
)
async def get_cross_document_comparison(
    request: Request, comparison_id: UUID
) -> ComparisonApiResponse:
    manager: JobManager = request.app.state.job_manager
    result = await manager.get_comparison(comparison_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found or expired.")
    return result


@router.get(
    "/jobs/{job_id}/evidence",
    response_model=EvidenceListResponse,
    summary="Get evidence produced by an extraction job",
)
async def get_job_evidence(request: Request, job_id: UUID) -> EvidenceListResponse:
    manager: JobManager = request.app.state.job_manager
    job = await manager.get_evidence(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if not job.status.is_terminal and job.extraction_result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evidence is not available until extraction has finished.",
        )
    return EvidenceListResponse(
        job_id=job.job_id,
        status=job.status,
        count=len(job.evidence),
        items=job.evidence,
    )


def _safe_filename(raw_filename: str | None) -> str:
    if not raw_filename:
        raise HTTPException(status_code=422, detail="A filename is required.")
    filename = PurePosixPath(raw_filename.replace("\\", "/")).name.strip()
    filename = "".join(character for character in filename if character.isprintable())
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=422, detail="The filename is invalid.")
    if len(filename) > 255:
        raise HTTPException(status_code=422, detail="The filename must be 255 characters or fewer.")
    return filename


def _supported_media_type(content_type: str | None, filename: str) -> str:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    extension = PurePosixPath(filename).suffix.lower()
    expected = {
        "application/pdf": ".pdf",
        "text/plain": ".txt",
    }
    if media_type not in expected:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported uploads are PDF (.pdf) and UTF-8 plain text (.txt).",
        )
    if extension != expected[media_type]:
        raise HTTPException(
            status_code=422,
            detail=f"The filename extension must be {expected[media_type]} for {media_type} uploads.",
        )
    return media_type


async def _read_limited_upload(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"The uploaded file exceeds the {max_bytes // (1024 * 1024)} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_content(media_type: str, content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if media_type == "application/pdf":
        if b"%PDF-" not in content[:1024]:
            raise HTTPException(status_code=422, detail="The uploaded file does not have a valid PDF header.")
        return
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="Plain-text uploads must be valid UTF-8.",
        ) from exc
