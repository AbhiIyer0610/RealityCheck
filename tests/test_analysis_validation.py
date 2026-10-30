from uuid import uuid4

from app.evidence.models import (
    ArtifactType, EvidenceObject, EvidenceProvenance, EvidenceType,
)
from app.reasoning.models import (
    Claim, ClaimCategory, ClaimKind, Finding, FindingStatus,
)
from app.reasoning.validation import validate_analysis_results


def evidence(evidence_type: EvidenceType) -> EvidenceObject:
    return EvidenceObject(
        evidence_type=evidence_type,
        content="The application must accept PDF files.",
        confidence=1.0,
        provenance=EvidenceProvenance(
            source_id="artifact-1", source_name="requirements.txt",
            artifact_type=ArtifactType.TEXT, extraction_method="test",
        ),
    )

def claim(item: EvidenceObject) -> Claim:
    return Claim(
        text="The application must accept PDF files.", category=ClaimCategory.REQUIREMENT,
        kind=ClaimKind.EXPLICIT, evidence_ids=[item.evidence_id], confidence=0.9,
    )

def finding(item: EvidenceObject, claim_item: Claim, status: FindingStatus) -> Finding:
    return Finding(
        title="Check", explanation="Test finding.", status=status,
        evidence_ids=[item.evidence_id], claim_ids=[claim_item.claim_id], confidence=0.9,
    )

def test_discards_claim_with_foreign_evidence_reference() -> None:
    item = evidence(EvidenceType.REQUIREMENT)
    bad = Claim(
        text="Invented", category=ClaimCategory.UNKNOWN, kind=ClaimKind.EXPLICIT,
        evidence_ids=[uuid4()], confidence=0.9,
    )
    claims, findings = validate_analysis_results([item], [bad], [])
    assert claims == []
    assert findings == []

def test_discards_finding_with_foreign_claim_reference() -> None:
    item = evidence(EvidenceType.REQUIREMENT)
    valid_claim = claim(item)
    bad_finding = Finding(
        title="Foreign claim", explanation="Should be discarded.",
        status=FindingStatus.UNCERTAIN, evidence_ids=[item.evidence_id],
        claim_ids=[uuid4()], confidence=0.7,
    )
    claims, findings = validate_analysis_results([item], [valid_claim], [bad_finding])
    assert claims == [valid_claim]
    assert findings == []

def test_downgrades_verified_finding_supported_only_by_requirement() -> None:
    item = evidence(EvidenceType.REQUIREMENT)
    valid_claim = claim(item)
    claims, findings = validate_analysis_results(
        [item], [valid_claim], [finding(item, valid_claim, FindingStatus.VERIFIED)]
    )
    assert len(claims) == 1
    assert len(findings) == 1
    assert findings[0].status == FindingStatus.UNCERTAIN
    assert findings[0].confidence <= 0.5
    assert "Verification guardrail" in findings[0].explanation

def test_keeps_verified_finding_with_observation_evidence() -> None:
    item = evidence(EvidenceType.OBSERVATION)
    valid_claim = claim(item)
    claims, findings = validate_analysis_results(
        [item], [valid_claim], [finding(item, valid_claim, FindingStatus.VERIFIED)]
    )
    assert len(claims) == 1
    assert len(findings) == 1
    assert findings[0].status == FindingStatus.VERIFIED
