"""Live end-to-end smoke test: upload a file and wait for Nebius claims/findings.

Run from the project root after configuring NEBIUS_API_KEY in .env and starting
RealityCheck's API server. This script never prints the API key.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Path to a .txt or .pdf sample file")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="RealityCheck API base URL")
    parser.add_argument("--timeout", type=float, default=420.0, help="Maximum total wait in seconds")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    path = args.file.expanduser().resolve()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2
    extension = path.suffix.lower()
    if extension not in {".txt", ".pdf"}:
        print("ERROR: choose a .txt or .pdf file", file=sys.stderr)
        return 2
    media_type = "application/pdf" if extension == ".pdf" else "text/plain"
    base_url = args.api.rstrip("/")
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=60.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            health = await client.get(f"{base_url}/ready")
            health.raise_for_status()
            with path.open("rb") as handle:
                response = await client.post(
                    f"{base_url}/api/v1/artifacts",
                    files={"file": (path.name, handle, media_type)},
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"ERROR: API request failed: {exc}", file=sys.stderr)
            return 2

        job = response.json()
        job_id = job["job_id"]
        print(f"Accepted upload: {path.name}")
        print(f"Job ID: {job_id}")
        print("Waiting for extraction and AI analysis...")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + args.timeout
        last_progress = None
        analysis = None
        while loop.time() < deadline:
            try:
                job_response = await client.get(f"{base_url}/api/v1/jobs/{job_id}")
                job_response.raise_for_status()
                job = job_response.json()
                analysis_response = await client.get(f"{base_url}/api/v1/jobs/{job_id}/analysis")
                analysis_response.raise_for_status()
                analysis = analysis_response.json()
            except httpx.HTTPError as exc:
                print(f"ERROR: failed while polling job: {exc}", file=sys.stderr)
                return 2

            progress = (job.get("status"), job.get("processing_stage"), job.get("progress_message"),
                        analysis.get("analysis_status"))
            if progress != last_progress:
                print(f"[{job.get('status')}] {job.get('processing_stage')}: {job.get('progress_message')}")
                last_progress = progress
            if job.get("status") in {"succeeded", "partial", "failed"}:
                break
            await asyncio.sleep(1.0)
        else:
            print(f"ERROR: timed out waiting for job {job_id}", file=sys.stderr)
            return 3

        evidence_response = await client.get(f"{base_url}/api/v1/jobs/{job_id}/evidence")
        if evidence_response.is_success:
            evidence = evidence_response.json()
            print(f"Evidence items: {evidence.get('count', 0)}")
        else:
            print(f"Evidence endpoint returned HTTP {evidence_response.status_code}")

        claims = analysis.get("claims", []) if analysis else []
        findings = analysis.get("findings", []) if analysis else []
        print(f"AI analysis status: {analysis.get('analysis_status') if analysis else 'unknown'}")
        print(f"Claims: {len(claims)}")
        for index, claim in enumerate(claims, start=1):
            print(f"  C{index}: {claim.get('text')} [{claim.get('category')}; evidence={len(claim.get('evidence_ids', []))}]")
        print(f"Findings: {len(findings)}")
        for finding in findings:
            print(f"  [{finding.get('status')}] {finding.get('title')}")
            print(f"    {finding.get('explanation')}")
        if job.get("status") == "failed":
            print(f"ERROR: extraction failed: {job.get('error_message')}", file=sys.stderr)
            return 1
        if analysis and analysis.get("analysis_status") == "failed":
            print(f"ERROR: AI analysis failed: {analysis.get('error_message')}", file=sys.stderr)
            return 1
        if not analysis or analysis.get("analysis_status") != "succeeded":
            print("ERROR: analysis did not complete. Confirm NEBIUS_API_KEY and model access.", file=sys.stderr)
            return 1
        print("\nPASS: upload -> extraction -> Nebius claims -> reconciliation findings completed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
