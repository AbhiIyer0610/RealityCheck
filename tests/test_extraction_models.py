import pytest
from uuid import uuid4
from pydantic import ValidationError

from app.core.provenance import EvidenceLocation
from app.ingestion.models import (
    ExtractedElement,
    ExtractedElementType,
    ExtractionResult,
    ExtractionStatus,
)


def test_extraction_result_with_text_table_and_image():
    artifact_id = uuid4()

    result = ExtractionResult(
        artifact_id=artifact_id,
        status=ExtractionStatus.SUCCESS,
        extractor_name="test-extractor",
        extractor_version="0.1.0",
        elements=[
            ExtractedElement(
                element_type=ExtractedElementType.TEXT,
                content="Customers may request a refund within 30 days.",
                location=EvidenceLocation(page=4),
                extraction_confidence=0.98,
            ),
            ExtractedElement(
                element_type=ExtractedElementType.TABLE,
                structured_content={
                    "headers": ["Region", "Refund Window"],
                    "rows": [
                        ["India", "30 days"],
                        ["US", "30 days"],
                    ],
                },
                location=EvidenceLocation(page=5),
                extraction_confidence=0.94,
            ),
            ExtractedElement(
                element_type=ExtractedElementType.IMAGE,
                content="Refund process architecture diagram",
                location=EvidenceLocation(
                    page=6,
                    bounding_box={
                        "x1": 0.10,
                        "y1": 0.20,
                        "x2": 0.80,
                        "y2": 0.70,
                    },
                ),
                extraction_confidence=0.89,
            ),
        ],
    )

    assert result.artifact_id == artifact_id
    assert result.status == ExtractionStatus.SUCCESS
    assert len(result.elements) == 3

    assert result.elements[0].element_type == ExtractedElementType.TEXT
    assert result.elements[1].element_type == ExtractedElementType.TABLE
    assert result.elements[2].element_type == ExtractedElementType.IMAGE

    assert result.elements[1].structured_content["rows"][0] == [
        "India",
        "30 days",
    ]

    assert result.elements[2].location.bounding_box.x1 == 0.10


def test_invalid_extraction_confidence_is_rejected():
    with pytest.raises(ValidationError):
        ExtractedElement(
            element_type=ExtractedElementType.TEXT,
            content="Some text",
            extraction_confidence=1.5,
        )


def test_partial_extraction_preserves_diagnostics():
    result = ExtractionResult(
        artifact_id=uuid4(),
        status=ExtractionStatus.PARTIAL,
        extractor_name="test-extractor",
        elements=[],
        diagnostics=[
            {
                "message": "Page 7 could not be extracted.",
                "severity": "error",
                "location": EvidenceLocation(page=7),
            }
        ],
    )

    assert result.status == ExtractionStatus.PARTIAL
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].location.page == 7