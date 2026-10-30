from evaluation.benchmark import load_cases
from app.reasoning.offline_demo import _has_context_mismatch, _has_semantic_scope_mismatch


def test_benchmark_cases_are_unique_and_well_formed() -> None:
    cases = load_cases()
    assert len(cases) >= 8
    assert len({case["id"] for case in cases}) == len(cases)
    assert any(case["expected_finding"] for case in cases)
    assert any(not case["expected_finding"] for case in cases)


def test_offline_heuristic_skips_explicitly_different_environments() -> None:
    assert _has_context_mismatch(
        "Development environment maximum upload size is 20 MB.",
        "Production environment maximum upload size is 80 MB.",
    )
    assert not _has_context_mismatch(
        "The maximum upload size is 50 MB.",
        "The maximum upload size is 80 MB.",
    )


def test_offline_heuristic_skips_explicitly_different_versions() -> None:
    assert _has_context_mismatch(
        "Version 1 maximum upload size is 50 MB.",
        "Version 2 maximum upload size is 80 MB.",
    )


def test_offline_heuristic_skips_warning_threshold_vs_hard_limit() -> None:
    assert _has_semantic_scope_mismatch(
        "Show a warning threshold when an upload reaches 75 MB.",
        "The maximum upload size is 80 MB.",
    )
    assert not _has_semantic_scope_mismatch(
        "The maximum upload size is 50 MB.",
        "The maximum upload size is 80 MB.",
    )


import asyncio

from evaluation.benchmark import evaluate_case


def test_duplicate_numeric_statements_do_not_duplicate_findings() -> None:
    case = {
        "id": "duplicate-source-facts",
        "expected_finding": True,
        "documents": [
            {"filename": "requirements.txt", "evidence_type": "requirement", "text": "The maximum upload size is 80 MB."},
            {"filename": "config.txt", "evidence_type": "configuration", "text": "MAX_UPLOAD_SIZE_MB=50\nThe maximum upload size is 50 MB."},
        ],
    }
    result = asyncio.run(evaluate_case(case))
    assert result["detected_finding"] is True
    assert result["finding_count"] == 1
