# RealityCheck documentation

**Document type:** Documentation index  
**Audience:** Hackathon reviewers, developers, testers, and future maintainers  
**Status:** Current project documentation as of 30th October 2026  
**Purpose:** Help readers find the right explanation without needing to inspect the source code first.

## Recommended reading order

1. [Project overview](01-project-overview.md) — understand what RealityCheck does and does not claim to do.
2. [Setup and configuration](02-setup-and-configuration.md) — install dependencies and start the app.
3. [User guide and demo](03-user-guide-and-demo.md) — run the single- and multi-document workflows.
4. [Architecture and data flow](04-architecture-and-data-flow.md) — understand the code structure and processing stages.
5. [Evidence model and RAG comparison](05-evidence-model-and-rag.md) — understand the core reasoning model and why retrieval-augmented generation alone is not enough.
6. [API reference](06-api-reference.md) — use the backend routes directly.
7. [Testing and evaluation](07-testing-and-evaluation.md) — verify code and interpret the small synthetic benchmark.
8. [Tavily external research](08-tavily-external-research.md) — use optional public web search safely.
9. [Security, limitations, troubleshooting](09-security-limitations-troubleshooting.md) — understand operational boundaries.

## Format and source policy

Each document uses the same top-level pattern: **Document information**, **Purpose**, **How it works / instructions**, **Example**, **Limitations**, and **Related documents**. Details are grounded in the code, configuration, tests, fixtures, and existing project notes in the supplied ZIP. Where the project archive does not include information—such as the official hackathon rubric—the documentation says so rather than inventing requirements.

## Source of truth

The repository code and tests define the current implementation. The documentation explains that implementation; it does not replace it. If a future code change alters a route, setting, or workflow, update the relevant document and its examples in the same change.
