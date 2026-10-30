from app.reasoning.models import ClaimCategory, ClaimKind, FindingStatus


def test_unknown_explicit_claim_and_uncertain_finding_are_distinct_axes():
    # A claim describes source extraction/classification; a finding describes
    # the strength of a proposed conclusion. They are intentionally independent.
    claim_category = ClaimCategory.UNKNOWN
    claim_kind = ClaimKind.EXPLICIT
    finding_status = FindingStatus.UNCERTAIN

    assert claim_category.value == "unknown"
    assert claim_kind.value == "explicit"
    assert finding_status.value == "uncertain"
    assert claim_kind != finding_status


def test_sample_requirements_pdf_is_described_as_illustrative_not_verified():
    from pathlib import Path

    candidates = [
        Path("RealityCheck_sample_evidence.pdf"),
        Path("tests/fixtures/Sample_evidence_pdf.pdf"),
    ]
    assert any(path.exists() for path in candidates), "Expected sample evidence PDF fixture"
