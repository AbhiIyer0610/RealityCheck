# RealityCheck

**AI-assisted, evidence-grounded claims analysis and reconciliation**

RealityCheck extracts evidence from uploaded documents, turns source statements into traceable claims, and produces review findings that link back to those claims and evidence. It supports single-document analysis, comparison of multiple documents, saved history, visual summaries, and optional user-triggered public web research through Tavily.

> **Important:** RealityCheck is a hackathon/local MVP for assisted review. A finding is not an independent audit, a guarantee of correctness, or proof of deployed runtime behavior. Review the cited source evidence and run the recommended checks before making operational decisions.

## Why RealityCheck?

Technical teams often work across requirements, implementation notes, configuration records, and test observations. These documents can describe related aspects of a system without establishing whether the expected behavior was actually implemented and verified.

RealityCheck helps engineering, QA, compliance, and audit teams connect claims to their source evidence, identify conflicting statements and verification gaps, and distinguish documented intent from observed results.

## How it works

1. **Ingest documents:** Upload PDF or UTF-8 text documents for extraction.
2. **Extract claims:** Identify meaningful statements, classify their evidence roles, and preserve source context and provenance.
3. **Reconcile evidence:** Compare claims with supplied evidence and reason across documents.
4. **Review findings:** Inspect verified, inferred, uncertain, and reality-gap findings with links to supporting claims and evidence.
5. **Compare documents:** Analyze multiple documents together to surface inconsistencies and dependencies.
6. **Optional external research:** Use the user-triggered Tavily panel to consult public web sources. External research is kept separate from uploaded-document evidence and does not itself create claims or change finding statuses.

## NVIDIA Nemotron and Nebius Token Factory

RealityCheck uses NVIDIA Nemotron models through the **Nebius Token Factory** hosted inference API:

| Model | Role in RealityCheck |
|---|---|
| `nvidia/nemotron-3-nano-30b-a3b` | Structured claim extraction from ingested documents |
| `nvidia/nemotron-3-super-120b-a12b` | Evidence reconciliation and reasoning across claims and supplied evidence |

The application uses separate model stages so extraction and deeper reconciliation have distinct responsibilities. The models are called from the Python backend through Nebius Token Factory's OpenAI-compatible API, using the base URL `https://api.tokenfactory.nebius.com/v1/`.

**How Token Factory helped:** It gave the project a hosted way to access and experiment with the Nemotron models through an API. This let development focus on integrating model capabilities into the document-analysis workflow, rather than provisioning and operating model-serving infrastructure. The complimentary credits made it practical to test the models during the hackathon.

The application supports three analysis-provider modes:

- `nebius` — live model-backed analysis using a configured Nebius API key.
- `offline` — deterministic demonstration heuristics; this is not semantic model reconciliation.
- `auto` — uses Nebius when a key is configured; otherwise, it falls back to extraction-only behavior without model-backed analysis.

## Technology

- **Backend:** Python, FastAPI
- **Frontend:** React, TypeScript, Vite
- **Document extraction:** Docling
- **AI inference:** NVIDIA Nemotron models through Nebius Token Factory
- **Persistence:** SQLite
- **Optional external research:** Tavily

## Documentation

Start with the [documentation index](docs/README.md).

| Document | What it covers |
|---|---|
| [Project overview](docs/01-project-overview.md) | Problem, goals, features, and current scope |
| [Setup and configuration](docs/02-setup-and-configuration.md) | Python, Conda, Node.js, environment variables, and run commands |
| [User guide and demo](docs/03-user-guide-and-demo.md) | Single uploads, multi-document comparison, history, visuals, and working examples |
| [Architecture and data flow](docs/04-architecture-and-data-flow.md) | Components, processing stages, persistence, and provider modes |
| [Evidence model and RAG comparison](docs/05-evidence-model-and-rag.md) | Claims, evidence, findings, guardrails, and why basic RAG is insufficient as the core method |
| [API reference](docs/06-api-reference.md) | Routes, request examples, and response behavior |
| [Testing and evaluation](docs/07-testing-and-evaluation.md) | Tests, benchmark commands, and interpretation |
| [Tavily external research](docs/08-tavily-external-research.md) | Intended use, setup, example, and trust boundaries |
| [Security, limitations, troubleshooting](docs/09-security-limitations-troubleshooting.md) | Safe use, known limits, and common problems |

## Quick start (Windows PowerShell)

### 1. Backend environment

From the project root:

```powershell
conda create -n realitycheck python=3.12 -y
conda activate realitycheck
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If the `realitycheck` Conda environment already exists, activate it instead of creating it again.

Edit the root `.env` file before starting the backend:

- For a no-model demonstration, set `ANALYSIS_PROVIDER=offline`.
- For live model analysis, set `ANALYSIS_PROVIDER=nebius` and replace the placeholder with a valid `NEBIUS_API_KEY`.
- `TAVILY_API_KEY` is optional. Leave it blank unless using the external research panel.
- Never commit `.env` or share real keys.

### 2. Start the backend

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend endpoints:

- Health: `http://127.0.0.1:8000/health`
- Readiness: `http://127.0.0.1:8000/ready`
- Interactive API docs: `http://127.0.0.1:8000/docs`

### 3. Start the frontend in a second terminal

```powershell
conda activate realitycheck
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). The frontend API base URL defaults to `http://127.0.0.1:8000`.

### 4. Verify the project

From the project root:

```powershell
python -m pytest -q
python -m compileall -q app evaluation tests
python scripts/run_evaluation.py
```

From `frontend`:

```powershell
npm run build
```

See the detailed [setup guide](docs/02-setup-and-configuration.md) and [testing guide](docs/07-testing-and-evaluation.md) for context and optional live-provider checks.

## License

This project is licensed under the [MIT License](LICENSE).
