# RealityCheck

**AI-assisted, evidence-grounded claims analysis and reconciliation**

RealityCheck extracts evidence from uploaded documents, turns source statements into traceable claims, and produces review findings that link back to those claims and evidence. It supports single-document analysis, comparison of multiple documents, saved history, visual summaries, and optional user-triggered public web research through Tavily.

> **Important:** RealityCheck is a hackathon/local MVP for assisted review. A finding is not an independent audit, a guarantee of correctness, or proof of deployed runtime behavior. Review the cited source evidence and run the recommended checks before making operational decisions.

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
