from __future__ import annotations

from uuid import UUID
from io import BytesIO
from typing import Any
from functools import lru_cache

from docling.datamodel.base_models import (
    ConversionStatus as DoclingConversionStatus,
    DocumentStream,
)
from docling.document_converter import DocumentConverter
from docling.exceptions import ConversionError
from docling_core.types.doc import CoordOrigin
from docling_core.types.doc.items.table.table import TableItem

from app.core.provenance import BoundingBox, EvidenceLocation
from app.ingestion.models import (
    ExtractedElement,
    ExtractedElementType,
    ExtractionDiagnostic,
    ExtractionResult,
    ExtractionStatus,
)


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    """Create one converter per worker process."""
    return DocumentConverter()


def convert_pdf_payload(
    filename: str,
    pdf_bytes: bytes,
    artifact_id: str,
    extractor_version: str,
) -> dict[str, Any]:
    """
    Convert a PDF inside a worker process.

    The return value contains only serialized domain data. Docling document
    objects never cross the process boundary.
    """

    converter = _get_converter()

    document_stream = DocumentStream(
        name=filename,
        stream=BytesIO(pdf_bytes),
    )

    try:
        conversion_result = converter.convert(
            document_stream,
            raises_on_error=False,
        )
    except ConversionError as exc:
        return _failed_payload(
            artifact_id=artifact_id,
            extractor_version=extractor_version,
            message=f"PDF conversion failed: {exc}",
            diagnostic_code="pdf_conversion_failed",
        )

    document = conversion_result.document
    elements: list[ExtractedElement] = []

    for item, _ in document.iterate_items():
        if item.label.value in {"section_header", "text"}:
            elements.append(
                ExtractedElement(
                    element_type=ExtractedElementType.TEXT,
                    content=item.text,
                    extraction_confidence=None,
                    location=_to_location(item=item, document=document),
                    metadata={"docling_label": item.label.value},
                )
            )

        elif isinstance(item, TableItem):
            elements.append(
                ExtractedElement(
                    element_type=ExtractedElementType.TABLE,
                    structured_content=_extract_table_content(item),
                    extraction_confidence=None,
                    location=_to_location(item=item, document=document),
                    metadata={
                        "docling_label": item.label.value,
                        "rows": item.data.num_rows,
                        "columns": item.data.num_cols,
                    },
                )
            )

    diagnostics = [
        ExtractionDiagnostic(
            message=error.error_message,
            severity=(
                "error"
                if conversion_result.status == DoclingConversionStatus.FAILURE
                else "warning"
            ),
            metadata={
                "source": "docling",
                "component": error.component_type.value,
                "category": error.category.value,
                **(
                    {"page": error.page_no}
                    if error.page_no is not None
                    else {}
                ),
            },
        )
        for error in conversion_result.errors
    ]

    if not elements:
        if not diagnostics:
            diagnostics.append(
                ExtractionDiagnostic(
                    message=(
                        "No supported text or table elements "
                        "were extracted from the PDF."
                    ),
                    severity="error",
                    metadata={
                        "source": "realitycheck",
                        "diagnostic_code": "no_supported_elements",
                    },
                )
            )

        result = ExtractionResult(
            artifact_id=UUID(artifact_id),
            status=ExtractionStatus.FAILED,
            elements=[],
            diagnostics=diagnostics,
            extractor_name="docling-pdf",
            extractor_version=extractor_version,
            metadata={
                "docling_status": conversion_result.status.value,
            },
        )
        return result.model_dump(mode="json")

    is_partial = (
        conversion_result.status != DoclingConversionStatus.SUCCESS
        or bool(diagnostics)
    )

    if (
        conversion_result.status == DoclingConversionStatus.PARTIAL_SUCCESS
        and not diagnostics
    ):
        diagnostics.append(
            ExtractionDiagnostic(
                message="Docling reported a partial conversion.",
                severity="warning",
                metadata={
                    "source": "docling",
                    "diagnostic_code": "partial_conversion",
                },
            )
        )

    result = ExtractionResult(
        artifact_id=UUID(artifact_id),
        status=(
            ExtractionStatus.PARTIAL
            if is_partial
            else ExtractionStatus.SUCCESS
        ),
        elements=elements,
        diagnostics=diagnostics,
        extractor_name="docling-pdf",
        extractor_version=extractor_version,
        metadata={
            "docling_status": conversion_result.status.value,
        },
    )

    return result.model_dump(mode="json")


def _failed_payload(
    *,
    artifact_id: str,
    extractor_version: str,
    message: str,
    diagnostic_code: str,
) -> dict[str, Any]:
    result = ExtractionResult(
        artifact_id=UUID(artifact_id),
        status=ExtractionStatus.FAILED,
        diagnostics=[
            ExtractionDiagnostic(
                message=message,
                severity="error",
                metadata={
                    "source": "realitycheck",
                    "diagnostic_code": diagnostic_code,
                },
            )
        ],
        extractor_name="docling-pdf",
        extractor_version=extractor_version,
    )
    return result.model_dump(mode="json")


def _to_location(
    *,
    item: Any,
    document: Any,
) -> EvidenceLocation | None:
    if not item.prov:
        return None

    provenance = item.prov[0]
    page = document.pages.get(provenance.page_no)

    if page is None or page.size is None:
        return None

    page_width = page.size.width
    page_height = page.size.height

    if page_width <= 0 or page_height <= 0:
        return None

    bbox = provenance.bbox

    x1 = bbox.l / page_width
    x2 = bbox.r / page_width

    if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
        y1 = 1.0 - (bbox.t / page_height)
        y2 = 1.0 - (bbox.b / page_height)
    elif bbox.coord_origin == CoordOrigin.TOPLEFT:
        y1 = bbox.t / page_height
        y2 = bbox.b / page_height
    else:
        raise ValueError(
            f"Unsupported Docling coordinate origin: {bbox.coord_origin}"
        )

    return EvidenceLocation(
        page=provenance.page_no,
        character_start=provenance.charspan[0],
        character_end=provenance.charspan[1],
        bounding_box=BoundingBox(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
        ),
    )


def _extract_table_content(table: TableItem) -> dict[str, object]:
    headers: list[str] = []
    rows: list[list[str]] = []

    for row in table.data.grid:
        if all(cell.column_header for cell in row):
            headers = [cell.text for cell in row]
            continue

        rows.append([cell.text for cell in row])

    return {
        "headers": headers,
        "rows": rows,
    }