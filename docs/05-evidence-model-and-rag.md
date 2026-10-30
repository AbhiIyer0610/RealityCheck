# 5. Evidence model, reconciliation, and the RAG distinction

**Document type:** Core technical concept  
**Audience:** Hackathon reviewers, AI engineers, and maintainers  
**Status:** Based on the current data models, reasoning flow, and validation code as of 30th October 2026  
**Purpose:** Explain what RealityCheck compares, how it preserves traceability, and why retrieval-augmented generation alone is not sufficient as the core solution.

## The core idea

RealityCheck is not designed only to retrieve a passage and generate an answer. Its central job is to turn source material into **structured, source-linked claims**, compare claims across evidence roles and documents, and produce findings whose references can be checked by the application and reviewer.

The data model separates:
- **Evidence:** content extracted from a source document, with evidence IDs and provenance information.
- **Claim:** a statement represented by text, category, kind, confidence estimate, and one or more evidence IDs.
- **Finding:** a proposed issue or evidence gap with a title, explanation, status, claim/evidence references, and optional recommendation, impact, alternative explanation, and validation test.

## Claim categories and kind

Claim category indicates the role of a statement:
- `intent`
- `requirement`
- `implementation`
- `configuration`
- `observation`
- `reference`
- `unknown`

Claim kind is:
- `explicit`: the statement is directly present in the source;
- `inferred`: the analyzer infers the statement.

**Explicit does not mean true.** It means the source explicitly says it. For example, an implementation note may explicitly state that a retry count is five, but that alone does not prove that the deployed process used that value.

## Finding status

The finding status enum contains:
- `verified`
- `inferred`
- `uncertain`
- `reality_gap`

These are analyzer classifications, not calibrated probabilities. A `reality_gap` can represent a missing connection between an expected requirement and the available implementation/observation evidence. An `uncertain` result signals that the available evidence is not strong enough to assert a firm conclusion.

The application validates the IDs returned by the analyzer. Claims that refer to evidence IDs not produced for the source are discarded. Findings with invalid evidence or claim references are discarded. The verification guardrail is conservative: the project documents that a model-produced `verified` status is downgraded unless the result has the required observation/implementation evidence basis and, in the claims-analysis checkpoint, corroboration across source artifacts. These checks improve reference integrity but do not prove that the underlying source statements are truthful.

## Why ordinary RAG is not enough here

### What a basic RAG flow typically does

A basic retrieval-augmented generation system:
1. indexes documents or passages;
2. retrieves passages relevant to a question;
3. supplies those passages to a language model; and
4. generates a response based on the retrieved context.

That is useful when the main task is to answer a question from a document collection. It can also be a useful supporting component in a larger system.

### The mismatch with RealityCheck's task

RealityCheck needs more than “retrieve the most relevant passages and summarize them”:

| Requirement in this project | Why retrieval plus a free-form answer alone is insufficient |
|---|---|
| Separate requirement, configuration, implementation, and observation claims | Similar words can have different roles. A requirement is not an observation, and a configuration note is not necessarily deployed state. |
| Compare statements across several sources | A response must preserve which source made each statement and whether they refer to the same environment, version, unit, or behavior. |
| Identify contradictions and missing proof | Retrieval can surface relevant passages, but relevance alone does not determine whether two claims conflict or whether a required test actually ran. |
| Keep findings traceable | The application expects structured claim/finding objects with IDs that point to extracted evidence and claims. A plausible paragraph with citations is not the same as a validated evidence graph. |
| Guard against fabricated references | The backend validates model-generated evidence and claim IDs against IDs it actually created. This is an application-level integrity check, not a feature guaranteed by RAG itself. |
| Preserve history and comparison records | RealityCheck persists jobs, evidence, claims, findings, and comparisons so results can be reopened and inspected. Retrieval by itself does not provide this workflow or lifecycle. |
| Distinguish absence of evidence from evidence of absence | A retrieval system returning no relevant passage does not prove that the requirement is satisfied or that a conflicting behavior does not exist. |

### Concrete example

Three documents contain:
- **Requirement:** “Transient upstream failures must result in no more than 3 total attempts.”
- **Configuration note:** “The retry wrapper is configured for 5 total attempts.”
- **QA observation:** “The client made 4 total attempts before reporting failure.”

A RAG answer may retrieve all three passages and summarize them. RealityCheck's intended output goes further: it represents each statement as a claim with source references, compares the roles and values, links the candidate finding to the relevant claim/evidence IDs, and lets the reviewer inspect the source material.

The QA observation supports what happened in that test run. It does not automatically prove every environment behaves the same way. A configuration note does not by itself prove the live deployed setting. The reconciliation must preserve those distinctions.

## Why RAG variants still do not replace the core workflow

- **Hybrid RAG** can improve retrieval recall by combining lexical and semantic retrieval, but it does not by itself impose the project's claim categories, contradiction logic, evidence-reference validation, or history model.
- **GraphRAG** can represent relationships among entities and passages, but a graph alone does not establish that a test executed or that an observation corroborates a requirement.
- **Agentic RAG** can orchestrate multiple searches or tools, but an agent's final answer still needs structured outputs, provenance checks, and explicit rules for what counts as a requirement, configuration, or observation.
- **Long-context prompting without retrieval** may fit more source text into a model call, but it still does not replace application-level ID validation, persistence, history, and the evidence/status semantics.

These techniques are not inherently useless. They could be added as supporting retrieval or navigation tools. The point is that **retrieval is not the core missing capability**: the core is evidence-grounded claim extraction and controlled reconciliation. A RAG component would need to feed that workflow rather than replace it.

## Where Tavily fits

Tavily is used only when the user explicitly asks to search public information. It is not used to decide whether internal documents contradict one another, and search results do not automatically become claims or change finding status. This separation keeps external context distinct from source-document evidence.

## Limitations

- The model can still misclassify claims or propose an incorrect finding.
- Confidence values are not calibrated truth probabilities.
- Evidence-reference validation proves that an ID exists in the supplied analysis, not that the content is true.
- The offline analyzer is a narrow deterministic demonstration heuristic and is not a semantic substitute for the live model-backed flow.
- Human review and targeted tests remain necessary for operational decisions.

## Related documents

- [Architecture and data flow](04-architecture-and-data-flow.md)
- [Testing and evaluation](07-testing-and-evaluation.md)
- [Tavily external research](08-tavily-external-research.md)
