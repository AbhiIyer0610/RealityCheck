import pytest
from uuid import uuid4
from types import SimpleNamespace

from docling.exceptions import ConversionError
from docling.datamodel.base_models import (
    ConversionStatus as DoclingConversionStatus,
)

from app.ingestion import docling_worker
from app.ingestion.models import ExtractionResult, ExtractionStatus


def _convert(
    monkeypatch: pytest.MonkeyPatch,
    fake_converter: object,
) -> ExtractionResult:
    monkeypatch.setattr(
        docling_worker,
        "_get_converter",
        lambda: fake_converter,
    )

    payload = docling_worker.convert_pdf_payload(
        filename="test.pdf",
        pdf_bytes=b"test PDF bytes",
        artifact_id=str(uuid4()),
        extractor_version="test",
    )

    return ExtractionResult.model_validate(payload)


def test_conversion_error_becomes_failed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingConverter:
        def convert(self, *args, **kwargs):
            raise ConversionError("Invalid PDF")

    result = _convert(monkeypatch, FailingConverter())

    assert result.status == ExtractionStatus.FAILED
    assert result.elements == []
    assert result.diagnostics[0].metadata["diagnostic_code"] == (
        "pdf_conversion_failed"
    )


def test_partial_conversion_preserves_elements_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_item = SimpleNamespace(
        label=SimpleNamespace(value="text"),
        text="Extracted text",
        prov=[],
    )
    document = SimpleNamespace(
        pages={},
        iterate_items=lambda: iter([(text_item, 0)]),
    )
    conversion_error = SimpleNamespace(
        error_message="A page could not be processed",
        component_type=SimpleNamespace(value="pipeline"),
        category=SimpleNamespace(value="inference_failure"),
        page_no=2,
    )
    conversion_result = SimpleNamespace(
        document=document,
        status=DoclingConversionStatus.PARTIAL_SUCCESS,
        errors=[conversion_error],
    )

    class PartialConverter:
        def convert(self, *args, **kwargs):
            return conversion_result

    result = _convert(monkeypatch, PartialConverter())

    assert result.status == ExtractionStatus.PARTIAL
    assert len(result.elements) == 1
    assert result.elements[0].content == "Extracted text"
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "warning"
    assert result.diagnostics[0].metadata["page"] == 2


def test_unexpected_conversion_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedFailureConverter:
        def convert(self, *args, **kwargs):
            raise RuntimeError("Unexpected internal error")

    monkeypatch.setattr(
        docling_worker,
        "_get_converter",
        lambda: UnexpectedFailureConverter(),
    )

    with pytest.raises(RuntimeError, match="Unexpected internal error"):
        docling_worker.convert_pdf_payload(
            filename="test.pdf",
            pdf_bytes=b"test PDF bytes",
            artifact_id=str(uuid4()),
            extractor_version="test",
        )