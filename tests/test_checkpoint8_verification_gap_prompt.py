from pathlib import Path


def test_checkpoint8_verification_gap_prompt_contract() -> None:
    source = Path("app/reasoning/nebius_client.py").read_text(encoding="utf-8")

    assert "Independently identify verification gaps" in source
    assert "even when configuration and documented implementation appear aligned" in source
    assert "absence of a test result is not evidence that implementation behavior failed" in source
    assert "Do not invent a mismatch when values agree" in source
    assert "cite both the relevant requirement/acceptance criterion and the observation" in source
    assert "Avoid duplicate findings for the same behavior" in source


def test_verification_gap_status_is_uncertain_not_reality_gap() -> None:
    source = Path("app/reasoning/nebius_client.py").read_text(encoding="utf-8")

    assert "For a verification gap alone, use `uncertain`, not `reality_gap`" in source
    assert "absence of a test result is not evidence that implementation behavior failed" in source
    assert "A test explicitly reported as not run produces an `uncertain` verification-gap finding" in source
    assert '"Timeout behavior remains unverified"' in source
