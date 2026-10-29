"""Pydantic models (request and response shapes) shared by both databases."""
from datetime import datetime, timezone
from typing import Optional, Union

from pydantic import BaseModel, field_validator

SOURCES = ["nuclear", "wind", "hydroelectric", "oil_and_gas", "coal", "solar", "biomass"]


def to_naive_utc(dt: datetime) -> datetime:
    """Both databases store times as UTC without a timezone label."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class Generation(BaseModel):
    nuclear: int
    wind: int
    hydroelectric: int
    oil_and_gas: int
    coal: int
    solar: int
    biomass: int


class GenerationPartial(BaseModel):
    nuclear: Optional[int] = None
    wind: Optional[int] = None
    hydroelectric: Optional[int] = None
    oil_and_gas: Optional[int] = None
    coal: Optional[int] = None
    solar: Optional[int] = None
    biomass: Optional[int] = None


class RecordCreate(BaseModel):
    timestamp: datetime
    consumption: int
    production: int
    generation: Generation

    _norm = field_validator("timestamp")(lambda cls, v: to_naive_utc(v))

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2030-01-01T00:00:00",
                "consumption": 6500,
                "production": 6400,
                "generation": {
                    "nuclear": 1400, "wind": 100, "hydroelectric": 1200,
                    "oil_and_gas": 1500, "coal": 1600, "solar": 0, "biomass": 30,
                },
            }
        }
    }


class RecordUpdate(BaseModel):
    """Every field is optional: send only what you want to change."""
    timestamp: Optional[datetime] = None
    consumption: Optional[int] = None
    production: Optional[int] = None
    generation: Optional[GenerationPartial] = None

    _norm = field_validator("timestamp")(
        lambda cls, v: to_naive_utc(v) if v is not None else v
    )

    model_config = {
        "json_schema_extra": {"example": {"consumption": 7000, "generation": {"wind": 250}}}
    }


class RecordOut(BaseModel):
    id: Union[int, str]
    timestamp: datetime
    consumption: int
    production: int
    generation: GenerationPartial