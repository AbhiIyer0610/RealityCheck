from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.evidence.models import EvidenceObject, EvidenceProvenance, EvidenceType, ArtifactType
from app.reasoning.models import Claim, FindingStatus
from app.reasoning.nebius_client import NebiusTokenFactoryAnalyzer


def _evidence() -> EvidenceObject:
    return EvidenceObject(
        evidence_type=EvidenceType.REQUIREMENT,
        content="The application must accept PDF files.",
        confidence=1.0,
        provenance=EvidenceProvenance(
            source_id="artifact-1", source_name="requirements.txt", artifact_type=ArtifactType.TEXT,
            extraction_method="text-extractor", extractor_version="0.1.0",
        ),
    )


@pytest.mark.asyncio
async def test_nebius_analyzer_extracts_only_claims_with_real_evidence_references() -> None:
    evidence = _evidence()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "nvidia/nemotron-3-nano-30b-a3b"
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        response_content = {
            "claims": [
                {"text": "The application must accept PDF files.", "category": "requirement", "kind": "explicit",
                 "evidence_ids": [str(evidence.evidence_id)], "confidence": 0.98},
                {"text": "Unsupported invented claim", "category": "requirement", "kind": "explicit",
                 "evidence_ids": [str(uuid4())], "confidence": 0.99},
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(response_content)}}]})

    settings = Settings(_env_file=None, nebius_api_key=SecretStr("test-key"))
    analyzer = NebiusTokenFactoryAnalyzer(settings, transport=httpx.MockTransport(handler))
    await analyzer.start()
    try:
        claims = await analyzer.extract_claims([evidence])
    finally:
        await analyzer.close()

    assert len(claims) == 1
    assert claims[0].evidence_ids == [evidence.evidence_id]
    assert claims[0].text == "The application must accept PDF files."


@pytest.mark.asyncio
async def test_nebius_analyzer_reconciles_findings_and_discards_untraceable_findings() -> None:
    evidence = _evidence()
    claim = Claim(
        text="The application must accept PDF files.", category="requirement", kind="explicit",
        evidence_ids=[evidence.evidence_id], confidence=0.95,
    )
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        assert body["model"] == "nvidia/nemotron-3-super-120b-a12b"
        response_content = {"findings": [
            {"title": "Implementation not demonstrated", "explanation": "The source states a requirement but does not show implementation evidence.",
             "status": "verified", "evidence_ids": [str(evidence.evidence_id)], "claim_indices": [0],
             "confidence": 0.8, "recommendation": "Upload implementation evidence.",
             "impact": "Users may rely on behavior that is not demonstrated.",
             "alternative_explanation": "The implementation may be documented elsewhere.",
             "validation_test": "Upload a small PDF and inspect the job response."},
            {"title": "Untraceable", "explanation": "No valid references.", "status": "verified",
             "evidence_ids": [str(uuid4())], "claim_indices": [100], "confidence": 1.0},
        ]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(response_content)}}]})

    settings = Settings(_env_file=None, nebius_api_key=SecretStr("test-key"))
    analyzer = NebiusTokenFactoryAnalyzer(settings, transport=httpx.MockTransport(handler))
    await analyzer.start()
    try:
        findings = await analyzer.reconcile([evidence], [claim])
    finally:
        await analyzer.close()

    assert calls == 1
    assert len(findings) == 1
    assert findings[0].status == FindingStatus.UNCERTAIN
    assert findings[0].claim_ids == [claim.claim_id]
    assert findings[0].evidence_ids == [evidence.evidence_id]
    assert "Verification guardrail" in findings[0].explanation
    assert findings[0].impact == "Users may rely on behavior that is not demonstrated."
    assert findings[0].alternative_explanation == "The implementation may be documented elsewhere."
    assert findings[0].validation_test == "Upload a small PDF and inspect the job response."


@pytest.mark.asyncio
async def test_nebius_analyzer_disables_thinking_and_reports_empty_content_clearly() -> None:
    evidence = _evidence()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["chat_template_kwargs"]["enable_thinking"] is False
        return httpx.Response(200, json={"choices": [{"message": {"content": None}, "finish_reason": "length"}]})

    settings = Settings(_env_file=None, nebius_api_key=SecretStr("test-key"))
    analyzer = NebiusTokenFactoryAnalyzer(settings, transport=httpx.MockTransport(handler))
    await analyzer.start()
    try:
        with pytest.raises(Exception, match="did not contain text JSON.*finish_reason=length"):
            await analyzer.extract_claims([evidence])
    finally:
        await analyzer.close()
