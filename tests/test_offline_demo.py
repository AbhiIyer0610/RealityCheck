from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.evidence.models import ArtifactType, EvidenceObject, EvidenceProvenance, EvidenceType
from app.reasoning.factory import create_claim_analyzer
from app.reasoning.models import FindingStatus
from app.reasoning.offline_demo import OfflineDemoAnalyzer


def _evidence() -> list[EvidenceObject]:
    return [EvidenceObject(
        evidence_type=EvidenceType.REQUIREMENT,
        content="The application must accept PDF files.", confidence=0.95,
        provenance=EvidenceProvenance(
            source_id="artifact-1", source_name="requirements.txt",
            artifact_type=ArtifactType.TEXT, extraction_method="test",
        ),
    )]

@pytest.mark.asyncio
async def test_offline_demo_is_deterministic_and_never_marks_findings_verified() -> None:
    analyzer = OfflineDemoAnalyzer()
    evidence = _evidence()
    claims_first = await analyzer.extract_claims(evidence)
    claims_second = await analyzer.extract_claims(evidence)
    assert [item.text for item in claims_first] == [item.text for item in claims_second]
    assert claims_first[0].evidence_ids == [evidence[0].evidence_id]
    findings = await analyzer.reconcile(evidence, claims_first)
    assert findings
    assert all(item.status == FindingStatus.UNCERTAIN for item in findings)
    assert all("offline demo" in item.title.lower() for item in findings)

def test_factory_selects_offline_without_api_key() -> None:
    settings = Settings(_env_file=None, analysis_provider="offline", nebius_api_key=None)
    analyzer = create_claim_analyzer(settings)
    assert isinstance(analyzer, OfflineDemoAnalyzer)
    assert analyzer.provider_name == "offline_demo"

def test_factory_auto_preserves_extraction_only_mode_without_key() -> None:
    settings = Settings(_env_file=None, analysis_provider="auto", nebius_api_key=None)
    assert create_claim_analyzer(settings) is None

def test_factory_requires_key_when_nebius_explicitly_selected() -> None:
    settings = Settings(_env_file=None, analysis_provider="nebius", nebius_api_key=None)
    with pytest.raises(ValueError, match="requires NEBIUS_API_KEY"):
        create_claim_analyzer(settings)


@pytest.mark.asyncio
async def test_offline_demo_splits_document_into_section_aware_claims() -> None:
    evidence = _evidence()
    evidence[0] = evidence[0].model_copy(update={
        "content": (
            "DEMO DOCUMENT\n"
            "Document ID: RC-1\n"
            "1. PURPOSE\n"
            "RealityCheck compares requirements with observed behavior.\n"
            "2. REQUIREMENTS\n"
            "R-001: The application must accept PDF files.\n"
            "R-002: The API must return a job identifier.\n"
            "3. IMPLEMENTATION NOTES\n"
            "The API stores jobs in SQLite.\n"
            "4. OBSERVED DEMO BEHAVIOR\n"
            "OBS-001: Uploading a text file returns a job identifier.\n"
        )
    })
    analyzer = OfflineDemoAnalyzer()
    claims = await analyzer.extract_claims(evidence)
    assert len(claims) == 5
    assert all(claim.evidence_ids == [evidence[0].evidence_id] for claim in claims)
    assert [claim.category.value for claim in claims] == [
        "intent", "requirement", "requirement", "implementation", "observation"
    ]
    assert all("Document ID" not in claim.text for claim in claims)
    assert all(len(claim.text) <= 500 for claim in claims)


@pytest.mark.asyncio
async def test_offline_demo_emits_one_summary_finding_not_repeated_fake_verdicts() -> None:
    analyzer = OfflineDemoAnalyzer()
    evidence = _evidence()
    claims = await analyzer.extract_claims(evidence)
    findings = await analyzer.reconcile(evidence, claims)
    assert len(findings) == 1
    assert findings[0].status == FindingStatus.UNCERTAIN
    assert findings[0].claim_ids == [claims[0].claim_id]
    assert "not a contradiction assessment" in findings[0].explanation


@pytest.mark.asyncio
async def test_offline_demo_returns_no_finding_when_no_claim_candidates_exist() -> None:
    analyzer = OfflineDemoAnalyzer()
    assert await analyzer.reconcile(_evidence(), []) == []
