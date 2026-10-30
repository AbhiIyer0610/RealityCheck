# 3. User guide and demo walkthrough

**Document type:** User guide and demo script  
**Audience:** Reviewers, testers, and users  
**Status:** Current UI workflows as on 30th October 2026  
**Purpose:** Explain how to use single-document analysis, multi-document comparison, visualizations, history, and optional external research.

## Main workflows

RealityCheck supports:
1. uploading and analyzing one PDF or TXT file;
2. uploading multiple documents and comparing their claims after each source job finishes;
3. reviewing evidence, claims, findings, source traceability, and visualizations;
4. reopening a saved analysis or comparison from Analysis History; and
5. optionally searching public sources with Tavily.

## A. Single-document analysis

1. Start the backend and frontend as described in [Setup](02-setup-and-configuration.md).
2. Choose the single-document upload workflow.
3. Select a `.pdf` or `.txt` file.
4. Wait for extraction and analysis stages to finish.
5. Inspect the evidence and its provenance, claims, findings, and visualizations.
6. Open source evidence referenced by a claim or finding before accepting the conclusion.

The API creates a job and returns a job ID. The UI polls job status and analysis status as processing continues. Evidence is available after extraction has completed; model analysis can have a separate status.

## B. Multi-document comparison

A comparison accepts **2–10 completed upload jobs**. In the UI, select the multi-document comparison workflow and upload the documents together. The frontend sends each document through the normal upload endpoint, waits for extraction and per-document analysis, then submits the completed job IDs to the comparison endpoint.

Do not treat an upload being accepted as proof that it is ready to compare. Each selected job must complete the required processing first.

### Included demonstration fixture pack

The repository contains a synthetic example under `tests/fixtures/`. The organizations, systems, identifiers, dates, and observations in this pack are fictional.

Recommended multi-document sequence:
- `02_product_requirements.pdf`
- `03_implementation_design.pdf`
- `04_production_configuration.pdf`
- `05_qa_execution_report.pdf`

These fixtures are intended to exercise mismatched requirements/configuration, runtime observations, and missing verification. The exact number and wording of findings may vary with model output. Judge whether each finding is grounded in the cited evidence rather than expecting an exact count.

### Example of a meaningful result

A requirement states a 45-second hard timeout. Implementation/configuration notes describe a 60-second worker timeout. A QA report records an elapsed time above 60 seconds and a retrying state. These statements support a candidate discrepancy, but the reviewer should still check that the documents refer to the same component, version, and environment.

A requirement that acceptance tests must be run is not itself a test result. Only an explicit observation or execution record can support a claim that a test actually ran.

## C. Read the visualizations correctly

The UI provides views including finding-status mix, source traceability, requirement-to-reality coverage links, evidence relationships, and an action triage board.

Interpret these as navigation and review aids:
- counts reflect the active result set;
- linked claims show how the analyzer connected source statements;
- action groupings are triage aids, not a calibrated risk score;
- absence of findings is not proof that the documents are correct; and
- model confidence is not a calibrated probability of truth.

Use chart filters to narrow the visible findings and clear the filter to restore the full list.

## D. Analysis History

History lists saved document analyses and comparisons in chronological order. A saved comparison is the main user-facing history item; its source jobs are grouped under it rather than duplicated as separate top-level items.

- Open a history item to restore its saved results without rerunning inference.
- Use **New analysis** to leave historical read-only mode and start another run.
- Deleting a saved comparison deletes the comparison record; its source jobs remain and can appear as standalone entries.
- Deleting a standalone document history item deletes its retained job and stored artifact.
- Active jobs cannot be deleted through the history endpoint.
- Bulk deletion is a sequence of requests, so partial success is possible and reported.

History returns at most the newest 100 items.

## E. Optional Tavily research

Use the collapsed **Optional external research** panel only when a question remains that public information can help answer. Example: whether official framework documentation describes an automatic upload-size limit.

Do not paste full internal documents, confidential findings, private URLs, or credentials into the search query. Tavily results are external references and do not automatically alter claims or finding status.

See [Tavily external research](08-tavily-external-research.md).

## Demo run-of-show

1. Start the app and show the main workspace.
2. Upload one synthetic document and inspect extracted evidence, claims, findings, and the finding visualizations.
3. Upload the same document again to demonstrate that a new analysis is created and history can show the repeated run.
4. Run a comparison with the four included `02`–`05` fixture PDFs.
5. Open one finding and follow its cited evidence back to the source.
6. Show the source traceability and requirement-to-reality views.
7. Open the comparison in History and explain that it is a saved result, not a rerun.
8. If configured, show Tavily as an optional, user-triggered side capability.
9. Close by explaining the limitations and the distinction between a candidate finding and independently verified runtime behavior.

## Limitations

- Model-backed outputs may vary; there is no promise of an exact findings count.
- PDF extraction quality depends on the source content and extraction result. Review diagnostics and extracted evidence for poor scans or complex layouts.
- Offline mode produces simulated output and is not a substitute for live semantic reconciliation.
- Synthetic fixtures are demonstrations, not evidence about a real production system.

## Related documents

- [Project overview](01-project-overview.md)
- [Evidence model and RAG comparison](05-evidence-model-and-rag.md)
