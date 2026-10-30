# 2. Setup and Configuration

**Document type:** Installation and operations guide  
**Audience:** Developers, hackathon reviewers, demo operators, and maintainers  
**Status:** Current project configuration as on 30th October 2026  
**Purpose:** Explain how to install, configure, run, and verify RealityCheck on Windows, Linux, and macOS.

---

## 1. Overview

RealityCheck consists of two independently started components:

1. **Backend:** A Python application built with FastAPI. It handles document uploads, extraction, evidence processing, claim analysis, reconciliation, history, and API requests.
2. **Frontend:** A React and TypeScript application built with Vite. It provides the user interface for uploading documents, viewing findings, comparing documents, and inspecting analysis history.

The backend and frontend run as separate processes during local development.

The backend uses SQLite for local persistence and a local directory for uploaded artifacts.

The application supports three analysis provider modes:

- `nebius`: Uses Nebius Token Factory for model-backed analysis.
- `offline`: Uses a deterministic demonstration analyzer without making model API calls.
- `auto`: Selects Nebius when an API key is configured; otherwise, analysis remains disabled.

Tavily is an optional external research capability and is not required for normal document analysis.

## 2. Prerequisites

The following software is required.

| Software | Requirement | Purpose |
|---|---|---|
| Python | 3.12 | Backend and document processing |
| Conda / Miniconda | Recommended | Python environment management |
| Node.js | `>=20.19.0` or `>=22.12.0` | Frontend development and build |
| npm | Installed with Node.js | Frontend dependency management |
| Git | Recommended | Source code management |

Python 3.12 is the environment used during project development.

The frontend's Node.js version requirement is defined in `frontend/package.json`. Check that file if the requirement changes in a future version.

### File System Permissions

RealityCheck requires read and write permissions for its local project data directory.

The application must be able to:

- Create the `data/` directory if it does not already exist.
- Create and modify the SQLite database file (`data/realitycheck.sqlite3`).
- Create, read, and delete files within `data/artifacts/` for uploaded documents and generated artifacts.
- Update database records during document processing, analysis, history management, and cleanup.

Ensure that the user running the backend has sufficient permissions to create directories and read/write files within the project data directory.

No separate SQLite server installation or database administrator privileges are required, as the application uses a local SQLite database.

### API credentials

The following credentials may be required depending on the selected features:

| Credential | Required? | Purpose |
|---|---|---|
| Nebius API key | Required for live model-backed analysis | Claim extraction and reconciliation |
| Tavily API key | Optional | User-triggered external web research |

Neither key is required to start the application in offline demonstration mode.

---

## 3. Windows Setup

The following instructions use Windows PowerShell.

### 3.1 Install Python environment

Install Miniconda or Anaconda if it is not already available.

Create the RealityCheck environment:

```powershell
conda create -n realitycheck python=3.12 -y
```

Activate the environment:

```powershell
conda activate realitycheck
```

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Install backend dependencies:

```powershell
python -m pip install -r requirements.txt
```

If the environment already exists, simply activate it instead of creating it again.

### 3.2 Configure backend environment

From the project root, create the environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure the required settings.

The available settings are described in Section 6.

### 3.3 Install frontend dependencies

Open a second PowerShell terminal.

Navigate to the frontend directory:

```powershell
cd frontend
```

Create the frontend environment file:

```powershell
Copy-Item .env.example .env
```

Install dependencies:

```powershell
npm ci
```

The `npm ci` command installs the dependencies using the versions recorded in `package-lock.json`.

---

## 4. Linux Setup

The following instructions use Ubuntu as the reference Linux distribution.

The same general process applies to other Linux distributions, although package installation commands may differ.

### 4.1 Install prerequisites

Install or configure the following:

- Python 3.12
- Conda or Miniconda
- Node.js meeting the version requirement in `frontend/package.json`
- npm

Conda/Miniconda is recommended for managing the Python environment.

If Conda is already installed, ensure that it is initialized for the shell being used.

### 4.2 Create the Python environment

From the project root:

```bash
conda create -n realitycheck python=3.12 -y
```

Activate it:

```bash
conda activate realitycheck
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install backend dependencies:

```bash
python -m pip install -r requirements.txt
```

### 4.3 Configure backend environment

Create the environment file:

```bash
cp .env.example .env
```

Open `.env` and configure the required settings.

For example:

```bash
nano .env
```

Use the configuration described in Section 6.

### 4.4 Install frontend dependencies

Open another terminal and navigate to the frontend directory:

```bash
cd frontend
```

Create the frontend environment file:

```bash
cp .env.example .env
```

Install dependencies:

```bash
npm ci
```

---

## 5. macOS Setup

The following instructions apply to macOS systems using either Apple Silicon or Intel processors.

### 5.1 Install prerequisites

Install or configure:

- Python 3.12
- Conda or Miniconda
- Node.js meeting the version requirement in `frontend/package.json`
- npm

Miniconda is recommended for managing the Python environment.

Ensure that Conda is initialized for the shell being used.

### 5.2 Create the Python environment

From the project root:

```bash
conda create -n realitycheck python=3.12 -y
```

Activate the environment:

```bash
conda activate realitycheck
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install backend dependencies:

```bash
python -m pip install -r requirements.txt
```

### 5.3 Configure backend environment

Create the environment file:

```bash
cp .env.example .env
```

Open it using a text editor:

```bash
nano .env
```

Configure the settings described in Section 6.

### 5.4 Install frontend dependencies

Open another terminal:

```bash
cd frontend
```

Create the frontend environment file:

```bash
cp .env.example .env
```

Install dependencies:

```bash
npm ci
```

### 5.5 Platform-specific considerations

The project uses document extraction dependencies, including Docling, which may have platform-specific native dependencies.

Installation behavior can differ between:
- Apple Silicon Macs;
- Intel-based Macs; and
- different Linux distributions.

If dependency installation fails, inspect the package installation error and the relevant dependency's platform support before changing pinned project dependencies.

Do not arbitrarily upgrade or replace dependencies as part of the initial setup.

---

## 6. Backend Configuration

The backend reads its configuration from the root `.env` file.

The `.env.example` file contains the available configuration variables and their default or example values.

### 6.1 Select the analysis provider

The `ANALYSIS_PROVIDER` setting determines how RealityCheck performs claim extraction and reconciliation.

#### Option A: Offline demonstration mode

```dotenv
ANALYSIS_PROVIDER=offline
NEBIUS_API_KEY=
TAVILY_API_KEY=
```

Offline mode uses a deterministic demonstration analyzer.

It does not call an external AI model.

This mode is useful for demonstrating the application's upload, extraction, evidence, and interface workflows without requiring a Nebius API key.

However, offline mode uses limited heuristic behavior. It does not provide the semantic reconciliation capability of the live model-backed workflow.

#### Option B: Nebius model-backed analysis

```dotenv
ANALYSIS_PROVIDER=nebius
NEBIUS_API_KEY=your_real_nebius_api_key
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_CLAIM_MODEL=nvidia/nemotron-3-nano-30b-a3b
NEBIUS_REASONING_MODEL=nvidia/nemotron-3-super-120b-a12b
```

Replace the example API key with a valid Nebius Token Factory API key.

The configured model defaults are:

| Purpose | Configured model |
|---|---|
| Claim extraction | `nvidia/nemotron-3-nano-30b-a3b` |
| Reasoning and reconciliation | `nvidia/nemotron-3-super-120b-a12b` |

Actual model availability depends on the user's Nebius account and service access.

For an initial access check, use:

```powershell
python scripts/check_nebius_access.py
```

The command is the same on Linux and macOS:

```bash
python scripts/check_nebius_access.py
```

The check sends an inference request and may consume API credits.

#### Option C: Automatic provider selection

```dotenv
ANALYSIS_PROVIDER=auto
```

In automatic mode:

- If a Nebius API key is configured, the application selects Nebius.
- If no Nebius API key is configured, analysis remains disabled and the application can still perform document extraction.

This differs from offline mode, which explicitly selects the demonstration analyzer.

### 6.2 Optional Tavily configuration

Tavily is used for user-triggered public web research.

To enable it, add a valid key to the root `.env`:

```dotenv
TAVILY_API_KEY=your_real_tavily_api_key
```

If Tavily is not configured, the external research capability remains unavailable.

This does not prevent normal document uploads, extraction, or reconciliation.

Restart the backend after changing the environment file.

**Security:** Never put Nebius or Tavily API keys in frontend environment variables, React source files, or GitHub commits.

### 6.3 Other application settings

The following settings are defined in the application's configuration.

| Variable | Default | Purpose |
|---|---:|---|
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum uploaded file size |
| `MAX_CONCURRENT_UPLOADS` | `4` | Concurrent upload processing limit |
| `MAX_CONCURRENT_EXTRACTIONS` | `2` | Extraction worker concurrency |
| `MAX_PENDING_EXTRACTION_JOBS` | `20` | Maximum pending extraction jobs |
| `MAX_CONCURRENT_LLM_CALLS` | `8` | Concurrent model-call limit |
| `LLM_TIMEOUT_SECONDS` | `60` | Model request timeout |
| `MAX_EXTRACTION_DURATION_SECONDS` | `300` | Extraction job deadline |
| `MAX_ANALYSIS_INPUT_CHARS` | `60000` | Maximum aggregate analysis input characters |
| `DATA_DIR` | `data` | Local database and artifact directory |
| `JOB_RETENTION_DAYS` | `30` | Retention period for terminal jobs |
| `JOB_CLEANUP_INTERVAL_SECONDS` | `3600` | Background cleanup interval |
| `ORPHAN_ARTIFACT_GRACE_SECONDS` | `3600` | Grace period for orphan artifact cleanup |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed frontend CORS origin |

The root `.env.example` and `app/core/config.py` are the source of truth for configuration.

Do not assume that the defaults in this guide override the values in your local `.env`.

---

## 7. Starting RealityCheck

The backend and frontend must run separately.

### 7.1 Start the backend

Activate the Python environment:

**Windows PowerShell / Linux / macOS:**

```powershell/bash
conda activate realitycheck
```

From the project root, start the FastAPI application:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend will be available at:

| Endpoint | Purpose |
|---|---|
| `http://127.0.0.1:8000/health` | Health check |
| `http://127.0.0.1:8000/ready` | Readiness check |
| `http://127.0.0.1:8000/docs` | Interactive API documentation |

Keep this terminal open while using the application.

### 7.2 Start the frontend

Open a second terminal.

Activate the environment if necessary:

```bash
conda activate realitycheck
```

Navigate to the frontend directory:

```bash
cd frontend
```

Start the development server:

```bash
npm run dev
```

Vite prints the local frontend URL in the terminal.

The default address is:

```text
http://localhost:5173
```

Open this address in your browser.

### 7.3 Verify the application

Check the backend health endpoint:

```text
http://127.0.0.1:8000/health
```

Check the readiness endpoint:

```text
http://127.0.0.1:8000/ready
```

Then open the frontend and verify that it can communicate with the backend.

---

## 8. Frontend Configuration

The frontend has its own environment file:

```text
frontend/.env
```

Create it from the supplied example:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

The frontend uses Vite environment variables for public configuration, including the backend API URL and client-side upload settings.

The default backend API URL is:

```text
http://127.0.0.1:8000
```

If the backend runs at a different address, update the frontend configuration accordingly.

**Important:** Frontend environment variables are exposed to the browser when used by the application. Never store provider secrets such as `NEBIUS_API_KEY` or `TAVILY_API_KEY` in `frontend/.env`.

Restart the Vite development server after changing frontend environment variables.

---

## 9. Testing and Verification

After installation, verify that the backend dependencies and frontend build are working.

### 9.1 Run the Python test suite

From the project root:

```bash
python -m pytest -q
```

This executes the project's automated Python tests.

### 9.2 Compile-check Python files

```bash
python -m compileall -q app evaluation tests
```

This checks Python files for compilation errors.

### 9.3 Run the evaluation benchmark

```bash
python scripts/run_evaluation.py
```

The script runs the curated evaluation cases using the configured evaluation behavior.

To save the report:

```bash
python scripts/run_evaluation.py --output evaluation/report.json
```

For a Nebius-backed evaluation:

```bash
python scripts/run_evaluation.py --provider nebius --output evaluation/nebius-report.json
```

The Nebius option requires a valid API key and may consume API credits.

The benchmark is a small curated regression set, not a measurement of general real-world accuracy.

### 9.4 Build the frontend

Navigate to the frontend directory:

```bash
cd frontend
```

Run:

```bash
npm run build
```

This performs the frontend TypeScript/build checks and creates the production build output.

### 9.5 Optional Nebius smoke test

From the project root, with a valid Nebius key configured:

```bash
python scripts/check_nebius_access.py
```

A document-level smoke test can also be run:

```bash
python scripts/smoke_test_nebius.py "path/to/sample-document.txt"
```

The smoke-test script accepts a supported PDF or TXT sample file.

Use a non-sensitive test document. Live model calls may consume API credits.

---

## 10. Common Commands Reference

The following commands are useful during development and demonstration.

| Task | Command |
|---|---|
| Create Conda environment | `conda create -n realitycheck python=3.12 -y` |
| Activate environment | `conda activate realitycheck` |
| Install Python dependencies | `python -m pip install -r requirements.txt` |
| Start backend | `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` |
| Run all Python tests | `python -m pytest -q` |
| Compile-check Python | `python -m compileall -q app evaluation tests` |
| Run evaluation | `python scripts/run_evaluation.py` |
| Check Nebius access | `python scripts/check_nebius_access.py` |
| Run Nebius smoke test | `python scripts/smoke_test_nebius.py "path/to/sample-document.txt"` |
| Install frontend dependencies | `npm ci` |
| Start frontend | `npm run dev` |
| Build frontend | `npm run build` |

The backend commands should be run from the project root.

The frontend commands should be run from the `frontend` directory.

---

## 11. Data Storage

By default, RealityCheck stores application data locally.

The configured data directory is:

```text
data/
```

The main local database is:

```text
data/realitycheck.sqlite3
```

Uploaded source files and related artifacts are stored under:

```text
data/artifacts/
```

The application uses the configured retention and cleanup settings for terminal jobs and orphaned artifacts.

The `data/` directory is excluded from source control.

**Do not manually modify the SQLite database or artifact files while the application is running.**

---

## 12. Troubleshooting

### 12.1 Conda command is not recognized

Verify that Conda/Miniconda is installed and initialized for the current shell.

On Windows, use an Anaconda/Miniconda PowerShell prompt if the regular PowerShell session does not recognize Conda.

On Linux/macOS, initialize Conda for the shell and open a new terminal.

### 12.2 Python dependency installation fails

Check:

- Python version;
- active Conda environment;
- pip version;
- the package installation error;
- platform-specific support for native dependencies.

Avoid changing pinned package versions without first identifying the failing dependency.

### 12.3 Backend fails to start

Check that:

- the current directory is the project root;
- the `realitycheck` environment is active;
- backend dependencies were installed;
- `.env` exists in the project root;
- the configured analysis provider has the required credentials.

### 12.4 Nebius analysis is unavailable

Check:

- `ANALYSIS_PROVIDER` is set correctly;
- `NEBIUS_API_KEY` is valid;
- the selected model is available to the account;
- the backend was restarted after changing `.env`.

Use the Nebius access-check script to investigate account/model access.

### 12.5 Upload returns HTTP 413

The uploaded file exceeds the configured upload limit.

Check `MAX_UPLOAD_SIZE_MB` in the root `.env`.

Also check the frontend upload-size setting if the browser rejects the file before sending it.

The backend limit is authoritative.

### 12.6 Analysis is not available after upload

Check the job and analysis states separately.

Extraction can complete even when model analysis is disabled or fails.

In `auto` mode without a Nebius key, extraction-only behavior is expected.

In `offline` mode, analysis uses simulated demonstration behavior.

For live analysis, inspect the backend logs and analysis error information.

### 12.7 Tavily search is unavailable

Check that:

- `TAVILY_API_KEY` is configured in the root `.env`;
- the backend was restarted after adding the key;
- the query is valid;
- the network and Tavily service are available.

Tavily is optional. Its failure should not prevent normal internal-document analysis.

### 12.8 Frontend cannot connect to the backend

Check that:

- the backend is running;
- the backend URL in `frontend/.env` is correct;
- the frontend origin matches the backend CORS configuration;
- both development servers are running.

Restart Vite after changing frontend environment variables.

### 12.9 Frontend build fails

Check the Node.js version against the requirement in `frontend/package.json`.

From `frontend/`, run:

```bash
npm ci
npm run build
```

Review the build output for TypeScript or dependency errors.

---

## 13. Platform Compatibility and Verification Status

RealityCheck is built using Python, FastAPI, SQLite, React, TypeScript, and Vite. Its application architecture is not intentionally tied to Windows.

However, platform-specific dependency installation behavior—particularly for document extraction dependencies—may differ between operating systems.

The development and verification environment used for this project was Windows 11 with Python 3.12, Miniconda, and PyCharm.

The Linux and macOS setup instructions are provided based on the project's current architecture and dependency configuration. They have not been independently validated through complete installation and end-to-end testing on those operating systems.

Therefore:

- Windows is the verified development environment.
- Ubuntu Linux setup is documented but not independently verified.
- macOS setup is documented but not independently verified.
- Apple Silicon and Intel macOS installations may have different native dependency behavior.

Users encountering platform-specific installation issues should inspect the relevant dependency's installation documentation before changing the project's pinned versions.

---

## 14. Operational Recommendations

For local development and hackathon demonstrations:

- Use one backend process.
- Keep the backend bound to `127.0.0.1`.
- Use synthetic documents for demonstrations.
- Keep API credentials in the root `.env`.
- Do not commit `.env`, uploaded documents, or generated database artifacts.
- Use the offline provider when demonstrating workflows without live model credentials.
- Use Nebius when demonstrating live claim extraction and reconciliation.
- Use Tavily only when external public research is relevant.

The current application is not designed for public production deployment without additional security, authentication, authorization, and operational controls.

---

## Related Documents

- [Project Overview](01-project-overview.md)
- [User Guide and Demo](03-user-guide-and-demo.md)
- [Architecture and Data Flow](04-architecture-and-data-flow.md)
- [API Reference](06-api-reference.md)
- [Testing and Evaluation](07-testing-and-evaluation.md)
- [Security, Limitations, and Troubleshooting](09-security-limitations-troubleshooting.md)