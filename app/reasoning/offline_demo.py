from __future__ import annotations

import json
import re
from itertools import combinations

from app.evidence.models import EvidenceObject
from app.reasoning.models import (
    Claim, ClaimCategory, ClaimKind, Finding, FindingStatus,
)


class OfflineDemoAnalyzer:
    """Deterministic, explicitly simulated analyzer for demos without API credentials.

    It turns extracted source text into short, source-linked claim candidates. It
    does not call a model, detect contradictions, or determine whether a statement
    is true outside the source document.
    """

    provider_name = "offline_demo"
    _MAX_CLAIMS = 40
    _MAX_CLAIM_CHARS = 500
    _MAX_REFERENCES_PER_FINDING = 30

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def extract_claims(self, evidence: list[EvidenceObject]) -> list[Claim]:
        claims: list[Claim] = []
        seen: set[tuple[str, str]] = set()
        for item in evidence:
            if len(claims) >= self._MAX_CLAIMS:
                break
            source_text = item.content
            if not source_text and item.structured_content:
                source_text = json.dumps(item.structured_content, ensure_ascii=False, sort_keys=True)
            if not source_text or not source_text.strip():
                continue

            fallback_category = _category_for_evidence(item.evidence_type.value)
            for statement, category in _extract_source_statements(source_text, fallback_category):
                normalized = " ".join(statement.split())
                dedupe_key = (normalized.casefold(), category.value)
                if not normalized or dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                claims.append(Claim(
                    text=normalized[: self._MAX_CLAIM_CHARS],
                    category=category,
                    kind=ClaimKind.EXPLICIT,
                    evidence_ids=[item.evidence_id],
                    # The model schema requires a numeric value. This is a neutral
                    # placeholder, not a calibrated truth/confidence estimate. The
                    # UI deliberately hides confidence scores in offline mode.
                    confidence=0.5,
                ))
                if len(claims) >= self._MAX_CLAIMS:
                    break
        return claims

    async def compare_documents(
        self, evidence: list[EvidenceObject], claims: list[Claim]
    ) -> list[Finding]:
        """Return conservative heuristic candidates across different source files.

        This intentionally recognizes only a few explicit numeric constraints. It is
        not semantic reasoning and never labels a candidate as verified.
        """
        evidence_by_id = {item.evidence_id: item for item in evidence}
        facts: list[tuple[Claim, EvidenceObject, str, float, str, str]] = []
        for claim in claims:
            fact = _extract_numeric_constraint(claim.text)
            if fact is None:
                continue
            topic, numeric_value, display_value, normalized_value = fact
            for evidence_id in claim.evidence_ids:
                item = evidence_by_id.get(evidence_id)
                if item is None:
                    continue
                facts.append((claim, item, topic, normalized_value, display_value, claim.text))
                break

        findings: list[Finding] = []
        seen_pairs: set[tuple[str, str, str]] = set()
        for left, right in combinations(facts, 2):
            left_claim, left_evidence, left_topic, left_value, left_display, left_text = left
            right_claim, right_evidence, right_topic, right_value, right_display, right_text = right
            if left_topic != right_topic or left_value == right_value:
                continue
            if left_evidence.provenance.source_id == right_evidence.provenance.source_id:
                continue
            # Do not compare values that are explicitly scoped to different
            # environments or versions. The offline mode cannot reconcile those
            # contexts reliably, so suppress the candidate rather than overstate it.
            if _has_context_mismatch(left_text, right_text):
                continue
            # A warning threshold and a hard maximum are different concepts even
            # when they use the same unit. The offline heuristic cannot reason
            # about that relationship safely, so leave it for model-backed review.
            if _has_semantic_scope_mismatch(left_text, right_text):
                continue
            # Multiple extracted statements can repeat the same numeric fact in
            # one source. Deduplicate at source-pair/topic level, not claim-ID level.
            pair_key = tuple(sorted((left_evidence.provenance.source_id, right_evidence.provenance.source_id)))
            if (left_topic, *pair_key) in seen_pairs:
                continue
            seen_pairs.add((left_topic, *pair_key))
            label = left_topic.replace("_", " ")
            findings.append(Finding(
                title=f"Possible {label} mismatch across documents",
                explanation=(
                    f"'{left_evidence.provenance.source_name}' states: {left_text[:450]}\n\n"
                    f"'{right_evidence.provenance.source_name}' states: {right_text[:450]}\n\n"
                    f"The offline heuristic found different numeric values ({left_display} vs {right_display}) "
                    f"for the same {label} topic. This is a review candidate, not a verified discrepancy: "
                    "the sources may describe different versions, environments, or intended defaults."
                )[:3000],
                status=FindingStatus.UNCERTAIN,
                evidence_ids=[left_evidence.evidence_id, right_evidence.evidence_id],
                claim_ids=[left_claim.claim_id, right_claim.claim_id],
                confidence=0.5,
                recommendation=(
                    "Confirm which source is authoritative, check the effective runtime configuration, "
                    "and add a regression test for the intended value."
                ),
                impact=(
                    "Different values may cause inconsistent behavior between the documented expectation "
                    "and the effective system setting."
                ),
                alternative_explanation=(
                    "The sources may describe different versions, environments, rollout stages, or different "
                    "kinds of threshold rather than a true contradiction."
                ),
                validation_test=(
                    "Read the effective runtime value in the target environment and run one boundary test "
                    "just below, at, and just above the intended limit."
                ),
            ))
            if len(findings) >= 10:
                return findings
        return findings

    async def reconcile(
        self, evidence: list[EvidenceObject], claims: list[Claim]
    ) -> list[Finding]:
        if not claims:
            return []
        evidence_by_id = {item.evidence_id: item for item in evidence}
        referenced_claims = claims[: self._MAX_REFERENCES_PER_FINDING]
        evidence_ids = list(dict.fromkeys(
            evidence_id
            for claim in referenced_claims
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence_by_id
        ))[: self._MAX_REFERENCES_PER_FINDING]
        if not evidence_ids:
            return []
        return [Finding(
            title="Offline demo: source claims only",
            explanation=(
                f"The offline demo split extracted text into {len(claims)} source-linked claim candidates. "
                "No model compared requirements with implementation or observations, and no claim was "
                "independently verified. This is a workflow preview, not a contradiction assessment."
            ),
            status=FindingStatus.UNCERTAIN,
            evidence_ids=evidence_ids,
            claim_ids=[claim.claim_id for claim in referenced_claims],
            confidence=0.5,
            recommendation="Configure Nebius Token Factory to run model-based claim reconciliation.",
        )]



def _has_context_mismatch(left: str, right: str) -> bool:
    """Conservatively reject explicit environment/version comparisons."""
    normalized_left = left.casefold()
    normalized_right = right.casefold()
    environment_groups = (
        {"development", "dev", "local"},
        {"test", "testing", "qa"},
        {"staging", "stage", "pre-production", "preproduction"},
        {"production", "prod", "live"},
    )
    for group in environment_groups:
        left_has = any(re.search(rf"\b{re.escape(term)}\b", normalized_left) for term in group)
        right_has = any(re.search(rf"\b{re.escape(term)}\b", normalized_right) for term in group)
        if left_has != right_has and (left_has or right_has):
            return True

    version_pattern = r"\b(?:version|ver|v)\s*[-:]?\s*(\d+(?:\.\d+){0,2})\b"
    left_versions = set(re.findall(version_pattern, normalized_left))
    right_versions = set(re.findall(version_pattern, normalized_right))
    return bool(left_versions and right_versions and left_versions.isdisjoint(right_versions))


def _has_semantic_scope_mismatch(left: str, right: str) -> bool:
    """Avoid comparing different kinds of numeric limits as if equivalent."""
    left_text = left.casefold()
    right_text = right.casefold()
    scopes = {
        "warning_threshold": ("warning threshold", "warn at", "warning at"),
        "hard_limit": ("maximum", "max upload", "hard limit", "upload limit", "must not exceed", "limit is"),
    }
    left_scopes = {name for name, phrases in scopes.items() if any(p in left_text for p in phrases)}
    right_scopes = {name for name, phrases in scopes.items() if any(p in right_text for p in phrases)}
    return bool(left_scopes and right_scopes and left_scopes.isdisjoint(right_scopes))

def _extract_source_statements(
    source_text: str,
    fallback_category: ClaimCategory,
) -> list[tuple[str, ClaimCategory]]:
    """Split extracted text into useful, line-sized source statements.

    Recognized section headings set a category. Headings, document metadata,
    blank lines, and separator lines are not emitted as claims. When a document
    has no recognized sections, ordinary non-heading lines are still retained.
    """
    statements: list[tuple[str, ClaimCategory]] = []
    current_category = fallback_category
    lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+)", "", line).strip()
        if not line or re.fullmatch(r"[=*_—-]{3,}", line):
            continue

        section_category = _section_category(line)
        if section_category is not None:
            current_category = section_category
            continue

        # Skip document-level metadata; these fields describe the file rather
        # than the requirements, implementation, or behavior being assessed.
        if re.match(
            r"^(?:document\s+(?:id|type)|version|owner|status|last\s+updated)\s*:",
            line,
            flags=re.IGNORECASE,
        ):
            continue

        # Skip stand-alone all-caps headings/titles, but preserve labelled
        # statements such as R-001: and OBS-001: because they contain mixed case.
        if re.fullmatch(r"[A-Z][A-Z0-9 &()/,_-]{2,}", line):
            continue

        # A paragraph can contain several sentences. Split only at sentence
        # boundaries followed by a likely sentence start; keep IDs and file
        # extensions intact in the original text.
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", line)
        for part in parts:
            statement = part.strip(" \t-•")
            if len(statement) < 12:
                continue
            if not re.search(r"[A-Za-z]{3,}", statement):
                continue
            statements.append((statement, current_category))

    return statements


def _section_category(line: str) -> ClaimCategory | None:
    normalized = re.sub(r"^\d+[.)]\s*", "", line).strip().rstrip(":").upper()
    normalized = re.sub(r"\s+", " ", normalized)
    section_map = {
        "PURPOSE": ClaimCategory.INTENT,
        "OBJECTIVE": ClaimCategory.INTENT,
        "INTENT": ClaimCategory.INTENT,
        "REQUIREMENTS": ClaimCategory.REQUIREMENT,
        "REQUIREMENT": ClaimCategory.REQUIREMENT,
        "IMPLEMENTATION": ClaimCategory.IMPLEMENTATION,
        "IMPLEMENTATION NOTES": ClaimCategory.IMPLEMENTATION,
        "CONFIGURATION": ClaimCategory.CONFIGURATION,
        "CONFIGURATION NOTES": ClaimCategory.CONFIGURATION,
        "OBSERVATION": ClaimCategory.OBSERVATION,
        "OBSERVATIONS": ClaimCategory.OBSERVATION,
        "OBSERVED BEHAVIOR": ClaimCategory.OBSERVATION,
        "OBSERVED DEMO BEHAVIOR": ClaimCategory.OBSERVATION,
        "REFERENCES": ClaimCategory.REFERENCE,
        "REFERENCE": ClaimCategory.REFERENCE,
    }
    return section_map.get(normalized)


def _category_for_evidence(value: str) -> ClaimCategory:
    try:
        return ClaimCategory(value)
    except ValueError:
        return ClaimCategory.UNKNOWN


def _extract_numeric_constraint(text: str) -> tuple[str, float, str, float] | None:
    """Extract a deliberately narrow numeric fact for offline comparison.

    Supported topics are upload-size limits, retention periods, and timeouts.
    Values are converted to a common base unit before comparison.
    """
    normalized = text.casefold().replace("_", " ").replace("-", " ")
    if re.search(r"upload|file size|uploaded file", normalized) and re.search(
        r"size|limit|maximum|max|exceed|upload", normalized
    ):
        topic = "upload_size"
        unit_pattern = r"bytes?|kib|kb|mib|mb|gib|gb"
        config_match = re.search(
            r"max\s+upload\s+size\s*(?P<keyunit>kb|mb|gb)\s*[:=]\s*(?P<value>\d+(?:\.\d+)?)",
            normalized,
        )
    elif re.search(r"retention", normalized) and re.search(r"day|hour|week", normalized):
        topic = "retention_period"
        unit_pattern = r"days?|weeks?|hours?"
        config_match = None
    elif re.search(r"timeout", normalized) and re.search(r"seconds?|minutes?|milliseconds?|ms\b", normalized):
        topic = "timeout"
        unit_pattern = r"milliseconds?|ms|seconds?|s\b|minutes?|mins?"
        config_match = None
    else:
        return None

    if config_match:
        value = float(config_match.group("value"))
        unit = config_match.group("keyunit")
    else:
        match = re.search(rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{unit_pattern})\b", normalized)
        if not match:
            return None
        value = float(match.group("value"))
        unit = match.group("unit")

    unit = unit.casefold()
    factors = {
        "b": 1.0, "byte": 1.0, "bytes": 1.0,
        "kb": 1000.0, "kib": 1024.0, "mb": 1_000_000.0, "mib": 1_048_576.0,
        "gb": 1_000_000_000.0, "gib": 1_073_741_824.0,
        "day": 86400.0, "days": 86400.0, "week": 604800.0, "weeks": 604800.0,
        "hour": 3600.0, "hours": 3600.0, "second": 1.0, "seconds": 1.0, "s": 1.0,
        "minute": 60.0, "minutes": 60.0, "min": 60.0, "mins": 60.0,
        "millisecond": 0.001, "milliseconds": 0.001, "ms": 0.001,
    }
    if unit not in factors:
        return None
    return topic, value, f"{value:g} {unit}", value * factors[unit]
