
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_demo_pack_is_explicitly_synthetic_and_contains_reconcilable_discrepancies() -> None:
    readme_md = FIXTURES / "README.md"
    readme_txt = FIXTURES / "README.txt"
    guide_path = readme_md if readme_md.exists() else readme_txt

    assert guide_path.exists(), (
        "Demo README not found in tests/fixtures/"
    )

    guide = guide_path.read_text(encoding="utf-8")
    requirements = (
        FIXTURES / "02_product_requirements.txt"
    ).read_text(encoding="utf-8")
    implementation = (
        FIXTURES / "03_implementation_design.txt"
    ).read_text(encoding="utf-8")
    configuration = (
        FIXTURES / "04_production_configuration.txt"
    ).read_text(encoding="utf-8")
    qa = (
        FIXTURES / "05_qa_execution_report.txt"
    ).read_text(encoding="utf-8")

    assert "fictional" in guide.lower()
    assert "45 seconds" in requirements
    assert "60 seconds" in implementation
    assert "MAX_UPLOAD_SIZE_MB=100" in configuration
    assert "61.4 seconds" in qa
    assert "HTTP 202 Accepted" in qa


def test_all_five_demo_document_text_fixtures_exist() -> None:
    expected_files = [
        "01_release_readiness_brief.txt",
        "02_product_requirements.txt",
        "03_implementation_design.txt",
        "04_production_configuration.txt",
        "05_qa_execution_report.txt",
    ]

    for filename in expected_files:
        path = FIXTURES / filename
        assert path.is_file(), f"Missing demo fixture: {path}"
        assert path.stat().st_size > 0, f"Demo fixture is empty: {path}"


def test_all_five_demo_pdf_fixtures_exist() -> None:
    expected_files = [
        "01_release_readiness_brief.pdf",
        "02_product_requirements.pdf",
        "03_implementation_design.pdf",
        "04_production_configuration.pdf",
        "05_qa_execution_report.pdf",
    ]

    for filename in expected_files:
        path = FIXTURES / filename
        assert path.is_file(), f"Missing demo PDF: {path}"
        assert path.stat().st_size > 0, f"Demo PDF is empty: {path}"
