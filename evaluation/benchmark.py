"""Small, repeatable benchmark for RealityCheck's conservative offline comparison.

This benchmark evaluates candidate-finding behavior on curated synthetic cases. It
is a regression signal, not a claim about real-world model quality or domain coverage.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.evidence.models import ArtifactType, EvidenceObject, EvidenceProvenance, EvidenceType
from app.core.config import Settings
from app.reasoning.factory import create_claim_analyzer
from app.reasoning.interfaces import ClaimAnalyzer
from app.reasoning.offline_demo import OfflineDemoAnalyzer

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "cases.json"


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark cases must be a non-empty JSON array.")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("Every benchmark case must have a string id.")
        if case["id"] in seen:
            raise ValueError(f"Duplicate benchmark case id: {case['id']}")
        seen.add(case["id"])
        if not isinstance(case.get("expected_finding"), bool):
            raise ValueError(f"Case {case['id']} must define expected_finding as a boolean.")
        documents = case.get("documents")
        if not isinstance(documents, list) or len(documents) < 2:
            raise ValueError(f"Case {case['id']} must contain at least two documents.")
        for document in documents:
            if not isinstance(document, dict) or not document.get("filename") or not document.get("text"):
                raise ValueError(f"Case {case['id']} contains an invalid document.")
    return cases


def _make_evidence(case_id: str, document: dict[str, str]) -> EvidenceObject:
    try:
        evidence_type = EvidenceType(document.get("evidence_type", "unknown"))
    except ValueError:
        evidence_type = EvidenceType.UNKNOWN
    return EvidenceObject(
        evidence_type=evidence_type,
        content=document["text"],
        confidence=1.0,
        provenance=EvidenceProvenance(
            source_id=f"benchmark:{case_id}:{document['filename']}",
            source_name=document["filename"],
            artifact_type=ArtifactType.TEXT,
            extraction_method="evaluation-fixture",
            extractor_version="benchmark-v1",
        ),
        metadata={"benchmark_case": case_id},
    )


async def evaluate_case(
    case: dict[str, Any], analyzer: ClaimAnalyzer | None = None
) -> dict[str, Any]:
    analyzer = analyzer or OfflineDemoAnalyzer()
    evidence = [_make_evidence(case["id"], doc) for doc in case["documents"]]
    claims = await analyzer.extract_claims(evidence)
    findings = await analyzer.compare_documents(evidence, claims)
    valid_evidence_ids = {item.evidence_id for item in evidence}
    valid_claim_ids = {item.claim_id for item in claims}
    citations_valid = all(
        all(ref in valid_evidence_ids for ref in finding.evidence_ids)
        and all(ref in valid_claim_ids for ref in finding.claim_ids)
        and bool(finding.evidence_ids or finding.claim_ids)
        for finding in findings
    )
    detected = bool(findings)
    expected = case["expected_finding"]
    return {
        "id": case["id"],
        "description": case.get("description", ""),
        "expected_finding": expected,
        "detected_finding": detected,
        "result": "TP" if expected and detected else "FN" if expected else "FP" if detected else "TN",
        "finding_count": len(findings),
        "citation_references_valid": citations_valid,
        "finding_titles": [finding.title for finding in findings],
        "claims": [
            {
                "claim_id": str(claim.claim_id),
                "text": claim.text,
                "category": claim.category.value,
                "kind": claim.kind.value,
                "evidence_ids": [str(item) for item in claim.evidence_ids],
                "confidence": claim.confidence,
            }
            for claim in claims
        ],
        "findings": [
            {
                "finding_id": str(finding.finding_id),
                "title": finding.title,
                "explanation": finding.explanation,
                "status": finding.status.value,
                "confidence": finding.confidence,
                "evidence_ids": [str(item) for item in finding.evidence_ids],
                "claim_ids": [str(item) for item in finding.claim_ids],
                "recommendation": finding.recommendation,
                "impact": finding.impact,
                "alternative_explanation": finding.alternative_explanation,
                "validation_test": finding.validation_test,
            }
            for finding in findings
        ],
    }


async def run_benchmark(path: Path = DEFAULT_CASES, provider: str = "offline") -> dict[str, Any]:
    cases = load_cases(path)
    if provider == "offline":
        analyzer: ClaimAnalyzer = OfflineDemoAnalyzer()
    elif provider == "nebius":
        settings = Settings(analysis_provider="nebius")
        selected = create_claim_analyzer(settings)
        if selected is None:
            raise RuntimeError("Nebius analysis is not configured; set NEBIUS_API_KEY before using --provider nebius.")
        analyzer = selected
    else:
        raise ValueError("Benchmark provider must be 'offline' or 'nebius'.")

    await analyzer.start()
    try:
        results = [await evaluate_case(case, analyzer) for case in cases]
    finally:
        await analyzer.close()
    counts = {key: sum(item["result"] == key for item in results) for key in ("TP", "FP", "TN", "FN")}
    precision = counts["TP"] / (counts["TP"] + counts["FP"]) if counts["TP"] + counts["FP"] else 0.0
    recall = counts["TP"] / (counts["TP"] + counts["FN"]) if counts["TP"] + counts["FN"] else 0.0
    specificity = counts["TN"] / (counts["TN"] + counts["FP"]) if counts["TN"] + counts["FP"] else 0.0
    total_findings = sum(item["finding_count"] for item in results)
    valid_finding_cases = sum(
        item["finding_count"] for item in results if item["citation_references_valid"]
    )
    return {
        "benchmark_name": "RealityCheck comparison benchmark",
        "benchmark_version": 1,
        "provider": provider,
        "scope_note": (
            "Synthetic regression cases; results are a small curated regression signal, not a measure of real-world accuracy."
            if provider == "nebius" else
            "Synthetic regression cases for a narrow heuristic; not a measure of model quality or real-world accuracy."
        ),
        "case_count": len(results),
        "counts": counts,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "finding_count_total": total_findings,
        "citation_reference_validity": round(valid_finding_cases / total_findings, 4) if total_findings else 1.0,
        "results": results,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Path to a benchmark cases JSON file")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON report")
    parser.add_argument("--provider", choices=("offline", "nebius"), default="offline",
                        help="Analyzer to benchmark; Nebius requires NEBIUS_API_KEY and may incur usage charges")
    args = parser.parse_args()
    report = asyncio.run(run_benchmark(args.cases, provider=args.provider))
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
