# 1. Project overview

**Document type:** Product and capability overview\
**Audience:** Reviewers, users, developers, and maintainers\
**Status:** Current implementation as on 30th October 2026\
**Purpose:** Explain the problem RealityCheck addresses, the workflows
it supports, its current capabilities, and potential directions for
future development.

## Purpose

RealityCheck is an AI-assisted evidence reconciliation application. It
accepts PDF and UTF-8 text documents, extracts evidence, builds claims
linked to that evidence, and produces findings that connect potential
inconsistencies or evidence gaps to their supporting source material.

It can analyze one document or compare claims from multiple uploaded
documents. A user can inspect source evidence, claims, findings, visual
summaries, and saved history rather than receiving only a free-form
answer.

## Problem being addressed

Documents that describe the same system can express different kinds of
statements:

-   What the system is required to do.
-   What an implementation or configuration document says.
-   What someone reports observing during execution.
-   What a reference document says.
-   What remains unknown or insufficiently supported.

Treating all these statements as interchangeable can produce misleading
conclusions. For example, a requirement that says a test *must* pass is
not evidence that the test was run or passed. A configuration note is
not necessarily proof of the deployed runtime setting.

RealityCheck represents claims by category and links them to extracted
evidence so a reviewer can inspect the basis of a finding.

## Main capabilities present in the source

-   Upload `.pdf` and `.txt` files for extraction.
-   Store extraction jobs, evidence, claims, findings, and source
    artifacts locally.
-   Use a configured Nebius Token Factory model flow for claim
    extraction and reconciliation.
-   Use a deterministic offline demonstration provider when configured;
    this provider does not call a model and has narrow heuristic
    behavior.
-   Compare **2--10 completed upload jobs** as one cross-document
    comparison.
-   Validate model-produced claim and finding references against
    evidence and claim IDs produced for the selected source set.
-   Keep saved document analyses and comparisons in history, reopen
    them, and delete retained history items.
-   Show finding status summaries, source traceability, claim/evidence
    relationships, requirement-to-reality coverage links, and an action
    triage view.
-   Run an optional, user-triggered Tavily search for public information
    without sending uploaded document text to Tavily.

## What a finding means

A finding is a review candidate supported by linked claims and/or
evidence. Its status is an analyzer classification, not an independently
measured probability or guarantee. The UI and documentation
intentionally avoid presenting the visualizations as a calibrated risk
score or proof of compliance.

The status labels in the data model are:

-   `verified`
-   `inferred`
-   `uncertain`
-   `reality_gap`

Claim categories are:

-   `intent`
-   `requirement`
-   `implementation`
-   `configuration`
-   `observation`
-   `reference`
-   `unknown`

Claim kind is `explicit` or `inferred`. These fields answer different
questions: a claim may be explicit in a source while the finding that
uses it remains uncertain.

## Typical use cases

-   Compare requirements with implementation or configuration notes.
-   Check whether a test observation supports or conflicts with a stated
    requirement.
-   Identify requirements for which no suitable observation or test
    evidence is supplied.
-   Review multiple documents together while keeping the origin of each
    claim visible.
-   Search public documentation when an external question remains after
    internal reconciliation.

## Example

Suppose a requirement document says the maximum upload size is 10 MiB, a
configuration note says 25 MiB, and no runtime test is supplied. The two
statements suggest a candidate mismatch if they refer to the same
endpoint, environment, units, and enforcement layer. The missing test
means the configured value should not be described as proven deployed
behavior.

## Future scope

The following are potential directions for extending RealityCheck beyond
its current implementation. They are not features currently provided by
the application or commitments about a future release.

### Broader document support

-   Add ingestion support for formats such as DOCX, XLSX, PPTX, and
    HTML.
-   Improve extraction coverage for scanned documents, handwritten
    content, complex tables, diagrams, and engineering drawings.
-   Provide format-specific extraction and validation where the
    structure of a document requires it.

### External systems and tool integrations

-   Explore MCP-based integrations to make approved external tools and
    systems accessible through controlled interfaces.
-   Connect to systems such as requirements management, issue tracking,
    test management, and engineering repositories wherever the domain document/s require them.
-   Support retrieving relevant records from connected systems while
    preserving their source identity and provenance.

### Deeper evidence and analysis capabilities

-   Improve cross-document traceability and change-impact analysis.
-   Identify contradictions, missing evidence, and changes in claims
    across document versions.
-   Support larger document collections and more advanced comparison
    strategies.
-   Improve the ability to distinguish missing evidence from evidence
    that directly contradicts a claim.
-   Allow users to attach tavily results as external reference/evidence and recompute claims and findings
### Observability and operational maturity

-   Extend observability for model usage, token consumption, latency,
    processing time, and estimated cost.
-   Explore scalable background processing and shared storage.
-   Add authentication, authorization, and multi-user workspace support
    before considering broader deployment.

These directions would need separate design, implementation, testing,
and security review. Their inclusion here does not imply that the
current MVP already supports them.

## Limitations

-   The application is a local, single-workspace MVP, not a production
    multi-tenant service.
-   A model-generated result can be wrong and requires human review.
-   Offline mode is a demonstration heuristic, not semantic
    reconciliation.
-   A finding or visualization does not independently prove deployed
    behavior.
-   The current upload workflow supports PDF and UTF-8 TXT files; other
    formats are not currently supported.
-   Extraction quality depends on the source document. Complex layouts
    and poor-quality scans may not be fully represented in extracted
    evidence.

## Related documents

-   [Evidence model and RAG comparison](05-evidence-model-and-rag.md)
-   [Architecture and data flow](04-architecture-and-data-flow.md)
-   [Security, limitations, and
    troubleshooting](09-security-limitations-troubleshooting.md)
