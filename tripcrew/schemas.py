"""Structured output models for every tool and for the final trip plan.

Mirrors the pattern used in the code-review-crew project: give each task an
output_pydantic model instead of trusting free-text output. That's what makes
the "evaluate the results" step in the agent loop possible in the first
place -- you can't sanity-check a blob of prose the same way you can check
a typed field.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Flight(BaseModel):
    origin: str = Field(description="Origin airport or city")
    destination: str = Field(description="Destination airport or city")
    departure_date: str = Field(description="ISO date of departure")
    airline: Optional[str] = Field(default=None)
    price_usd: Optional[float] = Field(default=None, description="Estimated or quoted price in USD")
    source: Literal["mocked", "aviationstack", "amadeus"] = Field(
        description="Where this data actually came from -- keep this honest, not decorative"
    )


class Hotel(BaseModel):
    name: str
    city: str
    check_in: str = Field(description="ISO date")
    check_out: str = Field(description="ISO date")
    price_per_night_usd: Optional[float] = Field(default=None)
    source: Literal["mocked", "amadeus"] = Field(
        description="Where this data actually came from"
    )
