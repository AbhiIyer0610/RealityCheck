import pytest
import asyncio
from pathlib import Path
from types import SimpleNamespace
from docling_core.types.doc import CoordOrigin
from docling_core.types.doc import BoundingBox as DoclingBoundingBox

from app.ingestion import docling_worker
from app.ingestion.pdf_extractor import PDFExtractor
from app.ingestion.models import Artifact, ExtractionStatus, ExtractedElementType, ExtractionResult, ArtifactStatus


class FileArtifactSource:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def read(self) -> bytes:
        return self._path.read_bytes()


class MemoryArtifactSource:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.fixture
def extractor() -> PDFExtractor:
    instance = PDFExtractor()
    yield instance
    asyncio.run(instance.shutdown())


def test_supports_pdf(extractor: PDFExtractor):
    artifact = Artifact(
        filename="refund_policy.pdf",
        media_type="application/pdf",
        size_bytes=123,
    )

    assert extractor.supports(artifact) is True


def test_does_not_support_text(extractor: PDFExtractor):
    artifact = Artifact(
        filename="example.txt",
        media_type="text/plain",
        size_bytes=123,
    )

    assert extractor.supports(artifact) is False


@pytest.mark.asyncio
async def test_extracts_refund_policy_pdf(extractor: PDFExtractor):
    pdf_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "refund_policy.pdf"
    )

    artifact = Artifact(
        filename="refund_policy.pdf",
        media_type="application/pdf",
        size_bytes=pdf_path.stat().st_size,
    )

    source = FileArtifactSource(pdf_path)

    result = await extractor.extract(
        artifact=artifact,
        source=source,
    )

    assert result.status == ExtractionStatus.SUCCESS
    assert result.artifact_id == artifact.artifact_id
    assert result.extractor_name == extractor.name
    assert result.extractor_version == extractor.version

    assert len(result.elements) == 3

    for element in result.elements:
        assert element.location is not None
        assert element.location.page == 1

        assert element.location.bounding_box is not None

        bounding_box = element.location.bounding_box

        assert 0.0 <= bounding_box.x1 <= 1.0
        assert 0.0 <= bounding_box.y1 <= 1.0
        assert 0.0 <= bounding_box.x2 <= 1.0
        assert 0.0 <= bounding_box.y2 <= 1.0

        assert bounding_box.x1 <= bounding_box.x2
        assert bounding_box.y1 <= bounding_box.y2

    assert result.elements[0].location.character_start == 0
    assert result.elements[0].location.character_end == 13

    assert result.elements[1].location.character_start == 0
    assert result.elements[1].location.character_end == 58

    contents = [
        element.content
        for element in result.elements
    ]

    assert "Refund Policy" in contents
    assert (
        "Customers may request a refund within 30 days of purchase."
        in contents
    )

    text_elements = [
        element
        for element in result.elements
        if element.element_type == ExtractedElementType.TEXT
    ]
    assert len(text_elements) == 2

    table_elements = [
        element
        for element in result.elements
        if element.element_type == ExtractedElementType.TABLE
    ]

    assert len(table_elements) == 1

    table = table_elements[0]
    assert table.structured_content == {
        "headers": ["Refund Type", "Window"],
        "rows": [
            ["Standard", "30 days"],
        ],
    }

    assert table.metadata["docling_label"] == "table"
    assert table.metadata["rows"] == 2
    assert table.metadata["columns"] == 2

    assert table.location is not None
    assert table.location.page == 1
    assert table.location.bounding_box is not None

    bbox = table.location.bounding_box
    assert 0.0 <= bbox.x1 <= bbox.x2 <= 1.0
    assert 0.0 <= bbox.y1 <= bbox.y2 <= 1.0


def test_to_location_converts_bottom_left_coordinates(
    extractor: PDFExtractor,
):
    document = SimpleNamespace(
        pages={
            1: SimpleNamespace(
                size=SimpleNamespace(
                    width=1000.0,
                    height=1000.0,
                )
            )
        }
    )

    item = SimpleNamespace(
        prov=[
            SimpleNamespace(
                page_no=1,
                bbox=DoclingBoundingBox(
                    l=100.0,
                    t=800.0,
                    r=400.0,
                    b=700.0,
                    coord_origin=CoordOrigin.BOTTOMLEFT,
                ),
                charspan=(0, 10),
            )
        ]
    )

    location = docling_worker._to_location(
        item=item,
        document=document,
    )

    assert location is not None
    assert location.page == 1
    assert location.character_start == 0
    assert location.character_end == 10

    assert location.bounding_box is not None
    assert location.bounding_box.x1 == pytest.approx(0.1)
    assert location.bounding_box.y1 == pytest.approx(0.2)
    assert location.bounding_box.x2 == pytest.approx(0.4)
    assert location.bounding_box.y2 == pytest.approx(0.3)


def test_to_location_preserves_top_left_coordinates(
    extractor: PDFExtractor,
):
    document = SimpleNamespace(
        pages={
            1: SimpleNamespace(
                size=SimpleNamespace(
                    width=1000.0,
                    height=1000.0,
                )
            )
        }
    )

    item = SimpleNamespace(
        prov=[
            SimpleNamespace(
                page_no=1,
                bbox=DoclingBoundingBox(
                    l=100.0,
                    t=200.0,
                    r=400.0,
                    b=300.0,
                    coord_origin=CoordOrigin.TOPLEFT,
                ),
                charspan=(5, 15),
            )
        ]
    )

    location = docling_worker._to_location(
        item=item,
        document=document,
    )

    assert location is not None
    assert location.page == 1
    assert location.character_start == 5
    assert location.character_end == 15

    assert location.bounding_box is not None
    assert location.bounding_box.x1 == pytest.approx(0.1)
    assert location.bounding_box.y1 == pytest.approx(0.2)
    assert location.bounding_box.x2 == pytest.approx(0.4)
    assert location.bounding_box.y2 == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_worker_failure_returns_failed_result() -> None:
    from app.ingestion.extraction_runtime import ExtractionWorkerError

    class FailingRuntime:
        async def extract_pdf(self, **kwargs):
            raise ExtractionWorkerError("Worker terminated unexpectedly")

    extractor = PDFExtractor(runtime=FailingRuntime())

    artifact = Artifact(
        filename="invalid.pdf",
        media_type="application/pdf",
        size_bytes=10,
    )

    result = await extractor.extract(
        artifact=artifact,
        source=MemoryArtifactSource(b"not a PDF"),
    )

    assert result.status == ExtractionStatus.FAILED
    assert result.artifact_id == artifact.artifact_id
    assert result.elements == []
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].metadata["diagnostic_code"] == (
        "extraction_worker_failed"
    )


@pytest.mark.asyncio
async def test_source_read_error_returns_failed_result(
    extractor: PDFExtractor,
) -> None:
    class FailingSource:
        async def read(self) -> bytes:
            raise OSError("Unable to read source")

    artifact = Artifact(
        filename="unreadable.pdf",
        media_type="application/pdf",
        size_bytes=10,
    )

    result = await extractor.extract(
        artifact=artifact,
        source=FailingSource(),
    )

    assert result.status == ExtractionStatus.FAILED
    assert result.elements == []
    assert len(result.diagnostics) == 1
    assert (
        result.diagnostics[0].metadata["diagnostic_code"]
        == "source_read_failed"
    )


@pytest.mark.asyncio
async def test_extracts_text_from_scanned_pdf_using_ocr(
    extractor: PDFExtractor,
) -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "scanned_refund_policy.pdf"
    )
    pdf_bytes = fixture_path.read_bytes()

    artifact = Artifact(
        filename=fixture_path.name,
        media_type="application/pdf",
        size_bytes=len(pdf_bytes),
        status=ArtifactStatus.RECEIVED,
    )

    source = FileArtifactSource(fixture_path)

    result = await extractor.extract(
        artifact=artifact,
        source=source,
    )

    assert result.status in {
        ExtractionStatus.SUCCESS,
        ExtractionStatus.PARTIAL,
    }
    assert result.elements, "OCR should extract usable content from the scanned PDF."

    extracted_text = " ".join(
        element.content
        for element in result.elements
        if element.content is not None
    ).casefold()

    assert "refunds are allowed within 30 days" in extracted_text

    text_elements = [
        element
        for element in result.elements
        if element.content is not None
    ]
    assert text_elements

    # OCR text must retain page provenance.
    assert any(
        element.location is not None
        and element.location.page == 1
        for element in text_elements
    )

    assert result.extractor_name == "docling-pdf"
    assert result.extractor_version


@pytest.mark.asyncio
async def test_extractor_does_not_block_event_loop() -> None:
    from app.ingestion.models import (
        ExtractedElement,
        ExtractedElementType,
    )

    class SlowRuntime:
        async def extract_pdf(self, **kwargs) -> ExtractionResult:
            await asyncio.sleep(0.2)
            return ExtractionResult(
                artifact_id=kwargs["artifact_id"],
                status=ExtractionStatus.SUCCESS,
                elements=[
                    ExtractedElement(
                        element_type=ExtractedElementType.TEXT,
                        content="Event loop remains responsive.",
                    )
                ],
                extractor_name="docling-pdf",
                extractor_version="test",
            )

    extractor = PDFExtractor(runtime=SlowRuntime())
    artifact = Artifact(
        filename="test.pdf",
        media_type="application/pdf",
        size_bytes=1,
    )

    heartbeat_ran = False

    async def heartbeat() -> None:
        nonlocal heartbeat_ran
        await asyncio.sleep(0.02)
        heartbeat_ran = True

    result, _ = await asyncio.gather(
        extractor.extract(
            artifact=artifact,
            source=MemoryArtifactSource(b"x"),
        ),
        heartbeat(),
    )

    assert result.status == ExtractionStatus.SUCCESS
    assert heartbeat_ran
