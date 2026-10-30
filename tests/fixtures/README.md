# RealityCheck demo evidence pack

**All organizations, systems, dates, identifiers, measurements, and results in this pack are fictional and created solely for demonstration.** They are realistic-style test artifacts, not claims about a real company or production system.

## Scenario

Meridian Document Intake is preparing a release of its document-processing service. The approved requirement specifies a 45-second hard timeout, a terminal failed state, a specific user-readable error, and a 50 MB upload limit. The implementation notes and production configuration describe different values and retry behavior. The QA report records test outcomes that conflict with the required behavior.

## Recommended UI demo sequence

1. **Single document:** Upload `01_release_readiness_brief.pdf` (or `.txt`). It combines requirements, configuration, implementation notes, and test observations in one artifact. Inspect extracted claims, findings, source citations, and the finding-mix chart.
2. **Cross-document:** Switch to Compare documents and upload `02_product_requirements.pdf`, `03_implementation_design.pdf`, `04_production_configuration.pdf`, and `05_qa_execution_report.pdf` together. Wait for every document to finish before the cross-document reconciliation runs.
3. Inspect finding explanations and source links, then open **Recommended action plan & triage board**, **Claims & evidence visualizations**, and **Source documents & processing details**.
4. Open a saved item in history and verify the upload controls are disabled. Use **New analysis** to leave historical mode.
5. Select several history entries with the checkboxes and use **Delete selected** to test bulk deletion. Deletion is sequential: if one deletion fails, the UI reports partial success rather than pretending the entire batch succeeded.

## Expected discrepancy themes

- 45-second requirement versus a 60-second worker timeout.
- Requirement for a terminal failed state versus implementation/configuration that retry timed-out jobs.
- Required actionable user-facing error versus generic `Processing failed` message.
- 50 MB upload limit versus a 100 MB configured limit and a recorded 60 MB acceptance.
- QA observations showing 61–62 seconds elapsed and a retrying state after 90 seconds.

Model outputs are nondeterministic. The UI may identify fewer or differently grouped findings. Evaluate whether each finding is grounded in cited evidence rather than expecting an exact title/count. Do not present this synthetic demo as a benchmark of real-world accuracy.
