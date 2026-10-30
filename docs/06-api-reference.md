# 6. API reference

**Document type:** Backend API reference  
**Audience:** Developers, testers, and integrators  
**Status:** Routes and schemas in the current source as on 30th October 2026  
**Purpose:** Document the main HTTP endpoints exposed by the FastAPI application.

## Base URL and interactive docs

Local base URL: `http://127.0.0.1:8000`

Interactive OpenAPI documentation: `http://127.0.0.1:8000/docs`

All application API routes below use the `/api/v1` prefix unless noted otherwise.

## Health and readiness

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Returns service health, name, version, and environment |
| `GET` | `/ready` | Checks that the job manager and local store are ready |

Example:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

## Upload and inspect a document job

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/artifacts` | Upload a PDF/TXT file and queue extraction; returns `202 Accepted` |
| `GET` | `/api/v1/jobs/{job_id}` | Get job state, stage, counts, timestamps, and diagnostics |
| `GET` | `/api/v1/jobs/{job_id}/evidence` | Get extracted evidence with provenance |
| `GET` | `/api/v1/jobs/{job_id}/analysis` | Get analysis status, claims, and findings |

Upload example using PowerShell's `curl.exe`:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/artifacts" `
  -H "accept: application/json" `
  -F "file=@C:\path\to\sample.pdf;type=application/pdf"
```

For a text file, use `type=text/plain` and a `.txt` file. The response includes `job_id`; copy it into subsequent requests.

Example status request:

```powershell
$jobId = "PASTE_JOB_UUID_HERE"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/jobs/$jobId"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/jobs/$jobId/evidence"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/jobs/$jobId/analysis"
```

Evidence retrieval returns `409 Conflict` while extraction is still pending/running and no extraction result is available. Poll the job endpoint and retry when extraction finishes.

## Cross-document comparisons

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/comparisons` | Compare 2–10 completed document jobs |
| `GET` | `/api/v1/comparisons/{comparison_id}` | Retrieve a saved comparison |

Request body:

```json
{
  "job_ids": [
    "PASTE_COMPLETED_JOB_UUID_1",
    "PASTE_COMPLETED_JOB_UUID_2"
  ]
}
```

PowerShell example:

```powershell
$body = @{
  job_ids = @(
    "PASTE_COMPLETED_JOB_UUID_1",
    "PASTE_COMPLETED_JOB_UUID_2"
  )
} | ConvertTo-Json

$comparison = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/comparisons" `
  -ContentType "application/json" `
  -Body $body

$comparison.comparison_id
```

Each job must exist and have completed extraction and claim analysis. Duplicate IDs are rejected. The comparison also enforces aggregate limits on claims, evidence, and analysis input.

## History

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/history` | List recent document analyses and comparisons |
| `DELETE` | `/api/v1/jobs/{job_id}/history` | Delete a completed document history item and its stored artifact |
| `DELETE` | `/api/v1/comparisons/{comparison_id}` | Delete a saved comparison record |

History returns up to the newest 100 entries. Source jobs referenced by a saved comparison are grouped under the comparison rather than duplicated as top-level history entries. Deleting a comparison does not delete its source jobs.

## Optional Tavily search

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/research/tavily/search` | Search public sources on explicit user request |

Request:

```json
{
  "query": "site:fastapi.tiangolo.com upload file size limit",
  "include_domains": ["fastapi.tiangolo.com"]
}
```

`query` must contain at least four non-whitespace characters and may be up to 500 characters. `include_domains` accepts up to 10 entries. The endpoint returns up to five results with title, URL, content snippet, and optional score. It does not send uploaded document text to Tavily.

If `TAVILY_API_KEY` is not configured, the endpoint returns `503`. The backend maps Tavily timeout, authentication, rate-limit, and other failures to API errors. Search results are external references, not proof of internal runtime behavior.

## Common response/error behavior

| Status | Meaning in common workflows |
|---|---|
| `202` | Upload accepted and queued |
| `201` | Comparison created |
| `400` | Invalid request metadata, such as malformed `Content-Length` |
| `404` | Unknown job or comparison |
| `409` | Requested evidence/comparison is not ready or an active job cannot be deleted |
| `413` | Request/upload exceeds configured upload limit |
| `422` | Invalid input, unsupported upload type, duplicate comparison IDs, or invalid comparison request |
| `502` | Upstream analysis/search failure |
| `503` | Service not ready, queue full, analysis provider unavailable, or Tavily not configured/rate limited |
| `504` | Tavily search timed out |

Exact details depend on the endpoint and error path; use `/docs` for the live schema.

## Limits

- Uploads are limited by `MAX_UPLOAD_SIZE_MB` (default 50).
- Supported uploads are PDF and UTF-8 TXT.
- Comparison requires 2–10 completed jobs and is subject to aggregate analysis limits.
- UUIDs identify records but do not provide authorization. The API has no user-level access control.

## Related documents

- [Architecture and data flow](04-architecture-and-data-flow.md)
- [Setup and configuration](02-setup-and-configuration.md)
- [Security, limitations, troubleshooting](09-security-limitations-troubleshooting.md)
