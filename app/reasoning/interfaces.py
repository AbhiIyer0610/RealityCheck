from __future__ import annotations

from typing import Protocol

from app.evidence.models import EvidenceObject
from app.reasoning.models import Claim, Finding


class ClaimAnalysisError(RuntimeError):
    """A sanitized provider/analysis failure suitable for displaying to the user."""


class ClaimAnalyzer(Protocol):
    """Application boundary for any provider that extracts claims and reconciles evidence."""

    provider_name: str

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def extract_claims(self, evidence: list[EvidenceObject]) -> list[Claim]: ...

    async def reconcile(
        self, evidence: list[EvidenceObject], claims: list[Claim]
    ) -> list[Finding]: ...
