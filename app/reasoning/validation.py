from __future__ import annotations

import logging
from uuid import UUID

from app.evidence.models import EvidenceObject, EvidenceType
from app.reasoning.models import Claim, Finding, FindingStatus

logger = logging.getLogger(__name__)


def validate_analysis_results(
    evidence: list[EvidenceObject],
    claims: list[Claim],
    findings: list[Finding],
) -> tuple[list[Claim], list[Finding]]:
    """Enforce traceability and conservative verification rules at the app boundary.

    Providers are not trusted to enforce their own evidence references. A claim is
    retained only when all its evidence IDs belong to this job. A finding is retained
    only when every reference resolves to this job's evidence or retained claims.
    """
    evidence_by_id = {item.evidence_id: item for item in evidence}
    valid_evidence_ids = set(evidence_by_id)
    valid_claims: list[Claim] = []
    seen_claim_ids: set[UUID] = set()

    for claim in claims:
        refs = claim.evidence_ids
        if (not refs or any(ref not in valid_evidence_ids for ref in refs)
                or claim.claim_id in seen_claim_ids):
            logger.warning("Discarded a claim with missing, foreign, or duplicate references")
            continue
        # Normalize duplicate evidence references while preserving order.
        normalized_refs = list(dict.fromkeys(refs))
        valid_claims.append(claim.model_copy(update={"evidence_ids": normalized_refs}))
        seen_claim_ids.add(claim.claim_id)

    claims_by_id = {item.claim_id: item for item in valid_claims}
    valid_findings: list[Finding] = []
    seen_finding_ids: set[UUID] = set()

    for finding in findings:
        if finding.finding_id in seen_finding_ids:
            logger.warning("Discarded a finding with a duplicate ID")
            continue
        if any(ref not in valid_evidence_ids for ref in finding.evidence_ids):
            logger.warning("Discarded a finding with a foreign evidence reference")
            continue
        if any(ref not in claims_by_id for ref in finding.claim_ids):
            logger.warning("Discarded a finding with a missing or foreign claim reference")
            continue
        evidence_refs = list(dict.fromkeys(finding.evidence_ids))
        claim_refs = list(dict.fromkeys(finding.claim_ids))
        if not evidence_refs and not claim_refs:
            logger.warning("Discarded a finding without traceable references")
            continue

        normalized = finding.model_copy(update={
            "evidence_ids": evidence_refs,
            "claim_ids": claim_refs,
        })
        if normalized.status == FindingStatus.VERIFIED:
            supporting_ids = set(evidence_refs)
            for claim_id in claim_refs:
                supporting_ids.update(claims_by_id[claim_id].evidence_ids)
            has_direct_support = any(
                evidence_by_id[item].evidence_type in {EvidenceType.IMPLEMENTATION, EvidenceType.OBSERVATION}
                for item in supporting_ids
            )
            if not has_direct_support:
                normalized = normalized.model_copy(update={
                    "status": FindingStatus.UNCERTAIN,
                    "explanation": (
                        normalized.explanation
                        + "\n\nVerification guardrail: downgraded because no implementation or observation evidence directly supports verification."
                    )[:3000],
                    "confidence": min(normalized.confidence, 0.5),
                })
        valid_findings.append(normalized)
        seen_finding_ids.add(finding.finding_id)

    return valid_claims, valid_findings
