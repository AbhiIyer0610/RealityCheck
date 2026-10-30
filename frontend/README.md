# RealityCheck frontend

React + Vite + TypeScript frontend for the existing FastAPI ingestion API.

## Requirements
- Node.js 20.19+ or 22.12+
- The RealityCheck FastAPI backend running locally

## Setup (Windows PowerShell)
```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```
Open the Vite URL printed in the terminal (normally http://localhost:5173).

The default API URL is `http://127.0.0.1:8000`. Change `VITE_API_BASE_URL` in `.env` if the backend runs elsewhere. `VITE_MAX_UPLOAD_SIZE_MB` is a client-side usability check; the backend's configured limit remains authoritative.

## Build check
```powershell
npm run build
```

## Current behavior
- Uploads `.pdf` and `.txt` artifacts as multipart form data.
- Displays the accepted job ID and polls the job endpoint while it is pending/running.
- Retrieves and renders evidence only after the job reaches a terminal state.
- Displays provenance, optional locations, extraction diagnostics, and structured content.
- Shows API errors, including queue-full/503 responses.

The frontend is a single-user local MVP. It does not implement login or user-level access control. Do not expose this app/backend publicly until authentication and authorization are implemented.
