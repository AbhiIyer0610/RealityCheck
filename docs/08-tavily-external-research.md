# 8. Optional Tavily external research

**Document type:** External research feature guide  
**Audience:** Users, reviewers, and maintainers  
**Status:** Current implementation as on 30th October 2026  
**Purpose:** Explain what Tavily does in RealityCheck, when to use it, and why its results must remain separate from internal evidence.

## Purpose and placement

Tavily is an optional, user-triggered public web search. It is purposely placed in a collapsed **Optional external research** panel so that it does not interrupt the main visualization and findings workflow.

Use it only when the supplied documents leave a question that public information can help answer—for example, official framework behavior, a public API specification, a vendor document, or a published standard.

## Current behavior

- The backend route is `POST /api/v1/research/tavily/search`.
- It requires `TAVILY_API_KEY` in the root `.env`.
- The query is limited to 500 characters and must contain at least four non-whitespace characters.
- Up to 10 optional domain restrictions can be supplied.
- The backend requests basic search, up to five results, without answer synthesis or raw content.
- Results shown by the application include title, URL, content snippet, and optional relevance score.
- Uploaded document text is not sent to Tavily.
- Search results do not automatically create claims, attach to findings, or change finding status.
- Without a key, the route returns a clear `503` response; normal internal-document analysis remains available.

## Configure it

Add a real key to the root `.env`:

```dotenv
TAVILY_API_KEY=your_real_tavily_api_key
```

Restart the backend after editing `.env`. Never place this key in `frontend/.env`, React code, source control, or a public issue.

## Recommended usage sequence

1. Reconcile the supplied documents first.
2. Identify the exact public question that remains unresolved.
3. Use a short, neutral search query.
4. Restrict domains to an authoritative source when appropriate.
5. Open and inspect the original source, including its version/date and applicability.
6. Keep the result labelled as external context in review notes.
7. Reassess only the question that the source actually helps answer.

## Worked example

Internal material contains:
- **Requirement:** uploads larger than 10 MiB must be rejected with HTTP 413;
- **Configuration note:** maximum upload size is 25 MiB;
- **Observation:** no test result or deployed-runtime measurement is supplied.

The internal documents already suggest a candidate mismatch if they refer to the same endpoint, environment, units, and enforcement layer. Tavily is not needed to identify that conflict.

A useful external question is whether the framework documentation describes an automatic upload-size limit:

```text
site:fastapi.tiangolo.com upload file size limit UploadFile request body limits
```

A result from official documentation may clarify framework behavior or point to the relevant configuration layer. It cannot prove that the actual application is configured for 10 or 25 MiB, that a reverse proxy has a particular setting, or that a real request returned HTTP 413. Those require source/configuration inspection and an explicit test or runtime observation.

## Good and bad queries

**Better:** a narrow public behavior question:

```text
site:docs.python.org/3.12/library asyncio timeout behavior
```

**Avoid:** pasting a complete internal finding, confidential document, proprietary code, customer information, private URL, or credentials into the search box.

## Trust boundaries

- Search results are untrusted external references.
- A relevance score is not a truth score.
- Prefer primary documentation and check version/date.
- External information cannot prove internal runtime state or test execution.
- Tavily is a discovery aid, not an automatic judge or replacement for claim/evidence reconciliation.

## Limitations

- Search results are not persisted as formal evidence in the current workflow.
- There is no “attach as external reference” action in the current implementation.
- Tavily availability, API key validity, rate limits, and network connectivity can affect search.
- External results must not automatically upgrade a finding to `verified`.

## Related documents

- [Evidence model and RAG comparison](05-evidence-model-and-rag.md)
- [API reference](06-api-reference.md)
- [Security, limitations, troubleshooting](09-security-limitations-troubleshooting.md)
