# 7. Testing and evaluation

**Document type:** Quality and verification guide  
**Audience:** Developers, reviewers, and maintainers  
**Status:** Commands and evaluation contract from the repository as on 30th October 2026\
**Purpose:** Explain how to run the tests and interpret the curated benchmark without overstating what it proves.

## Test layers present in the repository

The `tests/` directory includes checks for:
- evidence models and factories;
- extraction models, extractors, evidence mapping, and ingestion service;
- job store, job manager, retention, and hardening;
- analysis validation and claim-status semantics;
- Nebius analysis behavior;
- cross-document comparison;
- Tavily search endpoint behavior;
- UI contracts for history and finding visualizations; and
- offline demo behavior.

## Run the complete Python test suite

From the repository root, with the project environment active:

```powershell
conda activate realitycheck
python -m pytest -q
```

Run a focused group when investigating a feature:

```powershell
python -m pytest -q tests/test_cross_document_comparisons.py
python -m pytest -q tests/test_tavily_research.py
python -m pytest -q tests/test_ui_history_contract.py
```

Compile-check Python files:

```powershell
python -m compileall -q app evaluation tests
```

## Build the frontend

From `frontend/`:

```powershell
npm ci
npm run build
```

`npm ci` installs from the checked-in lock file. The build runs TypeScript checking and Vite production bundling.

## Run the synthetic evaluation benchmark

From the repository root:

```powershell
python scripts/run_evaluation.py
```

By default, this runs the curated benchmark with the offline provider and prints a JSON report.

Save a report:

```powershell
python scripts/run_evaluation.py --output evaluation/report.json
```

Run with the live Nebius analyzer:

```powershell
python scripts/run_evaluation.py --provider nebius --output evaluation/nebius-report.json
```

The Nebius option requires a configured key and may consume credits. Do not commit reports that contain sensitive source text if you adapt the cases for private projects.

## What the benchmark measures

The curated cases in `evaluation/cases.json` cover synthetic examples such as:
- a true numeric limit conflict;
- equivalent units;
- a warning threshold versus a hard limit;
- separate environments or versions;
- matching values;
- unrelated numbers; and
- other selected discrepancy/gap cases.

The report includes case-level TP/FP/TN/FN labels, precision, recall, specificity, and whether evidence/claim references are valid.

## How to interpret the result

The benchmark is a **small curated regression set**, not a representative measurement of real-world accuracy. The offline analyzer is intentionally narrow and heuristic; it does not perform general semantic reconciliation. A good score on this set must not be described as proof of broad accuracy.

Inspect individual cases and their findings, not only aggregate metrics. When a real failure is found, add a case that captures it and keep the expected outcome grounded in the case's source statements.

## Manual end-to-end verification

1. Start backend and frontend.
2. Upload a small `.txt` file.
3. Verify the job completes extraction and exposes evidence.
4. In live mode, verify claims and findings appear and link to valid evidence.
5. Upload two or more related files and compare them after each source job is complete.
6. Open the saved comparison from History and verify it restores without rerunning analysis.
7. Check the charts against the visible findings and clear any active chart filter.
8. If Tavily is configured, run a non-sensitive public query and verify the results remain separate from the formal findings.

## Limitations

- Model-backed outputs may be nondeterministic.
- Passing tests proves only the behaviors covered by those tests.
- The benchmark does not establish real-world accuracy.
- Live provider tests can use API credits and depend on account access/network conditions.

## Related documents

- [Architecture and data flow](04-architecture-and-data-flow.md)
- [Evidence model and RAG comparison](05-evidence-model-and-rag.md)
- [Setup and configuration](02-setup-and-configuration.md)
