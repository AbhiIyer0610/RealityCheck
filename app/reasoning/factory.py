from app.core.config import Settings
from app.reasoning.interfaces import ClaimAnalyzer
from app.reasoning.nebius_client import NebiusTokenFactoryAnalyzer
from app.reasoning.offline_demo import OfflineDemoAnalyzer


def create_claim_analyzer(settings: Settings) -> ClaimAnalyzer | None:
    """Select the configured analyzer without exposing provider details to job logic."""
    provider = settings.analysis_provider
    api_key = settings.nebius_api_key.get_secret_value().strip() if settings.nebius_api_key else ""

    if provider == "offline":
        return OfflineDemoAnalyzer()
    if provider == "nebius":
        if not api_key:
            raise ValueError("ANALYSIS_PROVIDER=nebius requires NEBIUS_API_KEY to be configured.")
        return NebiusTokenFactoryAnalyzer(settings)
    # auto preserves existing behavior: use Nebius when credentials are configured,
    # otherwise leave analysis disabled and continue extraction-only mode.
    if api_key:
        return NebiusTokenFactoryAnalyzer(settings)
    return None
