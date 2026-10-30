from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    """
    Coordinates for a region inside a visual artifact - normalized to the range 0.0 - 1.0.
    """

    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(frozen=True)


class EvidenceLocation(BaseModel):
    """
    Location of evidence inside its source artifact.
    Only the fields relevant to a particular artifact need to be populated.
    """

    page: int | None = Field(default=None, ge=1)

    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=0)

    bounding_box: BoundingBox | None = None

    record_id: str | None = None

    model_config = ConfigDict(frozen=True)