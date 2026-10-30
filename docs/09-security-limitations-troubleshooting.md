# 9. Security, limitations, and troubleshooting

**Document type:** Operational safety and troubleshooting guide\
**Audience:** Developers, demo operators, and reviewers\
**Status:** Current application boundaries defined as on 30th October 2026\
**Purpose:** Explain safe local use, known limitations, practical steps
for common failures, and areas that may require further development.

## Security and privacy

-   Keep `.env` local. It may contain `NEBIUS_API_KEY` and
    `TAVILY_API_KEY`.
-   Never put provider keys in frontend variables, source files,
    screenshots, chat messages, or Git commits.
-   `.gitignore` excludes `.env`, `.env.*`, `frontend/.env`, `data/`,
    Python caches, frontend `node_modules`, and build output.
-   Uploaded files may contain sensitive information. Only upload
    material you are authorized to process.
-   Live model analysis sends supplied evidence and claims to the
    configured hosted model provider. Use synthetic material for demos
    unless the document owner has approved the data handling.
-   Tavily receives the public search query and optional domain
    restrictions, not the uploaded document text. Do not paste
    confidential content into the query.
-   The app has no login, user ownership, or per-user authorization.
    UUIDs are not an access-control system. Keep it on localhost or
    behind a trusted boundary.

## Known limitations

### Analysis and model behavior

-   The live model may produce incorrect, incomplete, or inconsistently
    classified claims and findings. Human review is required.
-   Model output can vary between runs. The same documents and question
    are not guaranteed to produce identical results.
-   A claim marked `explicit` means the statement is represented as
    explicit in the source; it does not establish that the statement is
    true.
-   Finding statuses are analyzer classifications, not calibrated
    probabilities or independent measurements of correctness.
-   Reference validation checks whether returned claim and evidence
    references correspond to supplied records. It does not prove that
    the model interpreted those records correctly.
-   A finding can be missed, incorrectly raised, or assigned an
    unsuitable status. A reviewer should inspect the underlying evidence
    and context.
-   The offline analyzer is deterministic simulated output with narrow
    heuristics, not general semantic reconciliation.
-   The curated evaluation set is a regression aid, not a representative
    real-world accuracy benchmark.

### Document extraction

-   The current upload workflow supports PDF and UTF-8 TXT files. DOCX,
    XLSX, PPTX, HTML, and other formats are not currently supported by
    this workflow.
-   PDF extraction may not capture every detail in complex layouts,
    multi-column pages, multiple nested tables, poorly scanned documents, handwritten content,
    diagrams, or engineering drawings.
-   Poor scan quality, unusual fonts, rotated pages, or complex
    formatting can affect the quality and completeness of extracted
    content.
-   Extracted evidence should be reviewed against the original document,
    especially when a finding depends on a table, diagram, drawing, or
    precise technical value.
-   Successful extraction does not guarantee that every relevant
    statement in the source document was captured.

### Reconciliation and comparison

-   A difference between two claims is not automatically a
    contradiction. Scope, version, environment, units, date, and
    enforcement layer may explain an apparent mismatch.
-   A missing observation or test record does not prove that a test
    failed or that the system does not work.
-   Multi-document comparison requires completed source jobs with
    successful claim analysis. It currently supports 2--10 selected
    upload jobs.
-   Comparison input is bounded by the current limits of up to 120
    claims, up to 1,000 evidence objects, and the configured aggregate
    analysis-input character limit.
-   Comparison reconciliation occurs during the API request; it is not
    implemented as a separate persisted background comparison job
    lifecycle.

### External research

-   Tavily search is optional and user-triggered. Search results may be
    incomplete, outdated, or unrelated to the exact system version or
    environment being reviewed.
-   Search result titles and snippets are not authoritative proof of
    internal implementation, configuration, or runtime behavior.
-   Tavily results do not automatically become application claims or
    evidence and do not change finding statuses.
-   External search depends on Tavily availability, credentials, rate
    limits, network connectivity, and request timeouts.

### Deployment and operations

-   The app is a single-workspace MVP using local SQLite, local artifact
    storage, and an in-process queue.
-   Multiple Uvicorn worker processes are not supported safely with the
    current queue/store arrangement.
-   Distributed workers, shared storage, authentication/authorization,
    rate limiting, malware scanning, and production-grade
    retention/audit controls are not implemented.
-   The extraction deadline is a job-lifecycle deadline; it is not
    guaranteed to hard-kill a stuck native Docling process.
-   Local filesystem access is required to create and update the SQLite
    database and stored artifacts.
-   The application has not been established as a production-ready,
    multi-user or internet-facing service.

## Troubleshooting

### Backend fails to start with `ANALYSIS_PROVIDER=nebius`

-   Confirm `NEBIUS_API_KEY` is a real non-empty key.
-   Confirm `.env` is in the project root and the backend is started
    from the project root.
-   Restart the backend after changing `.env`.
-   If unsure whether the key/model is accessible, run
    `python scripts/check_nebius_access.py`.

### Upload returns `413`

The uploaded request or file exceeds the configured limit. Check
`MAX_UPLOAD_SIZE_MB` in `.env`, restart the backend, and verify the
frontend's `VITE_MAX_UPLOAD_SIZE_MB` if its client-side usability check
rejects the file earlier. The backend limit is authoritative.

### Upload is accepted but claims/findings are absent

-   Check the job status and `analysis_status` separately.
-   In `auto` mode without a Nebius key, extraction-only mode is
    expected.
-   In `offline` mode, output is simulated and limited.
-   In live mode, inspect `analysis_error_message` and backend logs.
-   Review the extracted evidence before treating a missing finding as
    meaningful.

### Comparison says a source job is not ready

Wait until every selected document has completed extraction and claim
analysis. The comparison endpoint rejects unknown jobs, duplicate IDs,
failed or in-progress jobs, and jobs without successful claim analysis.

### Comparison exceeds content limits or times out

Compare fewer or smaller documents. The current comparison limits
include 120 claims, 1,000 evidence objects, and the configured aggregate
analysis-input character limit. Comparison analysis occurs during the
request.

### Tavily returns `503`, `502`, or `504`

-   `503` can mean Tavily is not configured or the upstream rate limit
    was reached.
-   `502` can mean Tavily rejected the key or the upstream request
    failed.
-   `504` indicates a search timeout.
-   Confirm `TAVILY_API_KEY` in the root `.env`, restart the backend,
    and retry with a shorter public query. Normal internal-document
    reconciliation should remain usable without Tavily.

### Frontend cannot reach the backend

-   Confirm the backend is running on `http://127.0.0.1:8000`.
-   Check `VITE_API_BASE_URL` in `frontend/.env`.
-   Check `FRONTEND_ORIGIN` in the root `.env` if the frontend runs at a
    different origin.
-   Restart Vite after changing frontend environment variables.

### Frontend build fails

Run `npm ci` from `frontend/`, then `npm run build`. Check the Node.js
version against the `engines` declaration in `frontend/package.json`.

## Operational guidance

Currently, use local-only binding
(`127.0.0.1`), synthetic documents, and one API process. Do not expose
the application publicly as-is.

## Related documents

-   [Project overview](01-project-overview.md)
-   [Setup and configuration](02-setup-and-configuration.md)
-   [Architecture and data flow](04-architecture-and-data-flow.md)
-   [API reference](06-api-reference.md)
-   [Testing and evaluation](07-testing-and-evaluation.md)
