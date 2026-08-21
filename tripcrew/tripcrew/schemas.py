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


class Attraction(BaseModel):
    name: str
    city: str
    category: Optional[str] = Field(default=None, description="e.g. museum, park, landmark")
    estimated_cost_usd: Optional[float] = Field(default=None)


class WeatherReport(BaseModel):
    city: str
    date: str = Field(description="ISO date")
    summary: str = Field(description="Short human-readable forecast, e.g. 'light rain, 14C'")


class Budget(BaseModel):
    flights_usd: float = 0
    hotel_usd: float = 0
    attractions_usd: float = 0
    total_usd: float = 0
    unpriced_categories: list[str] = Field(
        default_factory=list,
        description="Categories left out of total_usd because no price data was "
        "available for them (e.g. Geoapify never returns attraction costs). "
        "Exists so a total that excludes something is never presented as if it "
        "were complete -- same honesty rule as the source field on Flight and "
        "Hotel, applied to what got silently treated as free instead of unknown.",
    )

    def recompute(self) -> "Budget":
        """Recompute total from the parts instead of trusting a model-written number.

        This is the cheap, non-LLM sanity check Constellate's groundedness bug
        should have taught us to always add: don't let the agent state a total,
        derive it.
        """
        self.total_usd = self.flights_usd + self.hotel_usd + self.attractions_usd
        return self


class TripPlan(BaseModel):
    destination: str
    days: int
    flights: list[Flight] = Field(default_factory=list)
    hotel: Optional[Hotel] = None
    attractions: list[Attraction] = Field(default_factory=list)
    weather: list[WeatherReport] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    open_questions: list[str] = Field(
        default_factory=list,
        description="Anything the agent needed from the user but didn't have -- "
        "populated instead of guessing",
    )


class TripQuestionIntent(BaseModel):
    """Output of the follow-up chatbot's classification step (see
    followup.py). Deliberately thin: the LLM only picks which part of an
    already-finished TripPlan a question is about, it never sees or writes
    the actual answer. Answering is plain Python, reading real fields off
    TripPlan -- that split is what "graph traversal, not a RAG pipeline"
    (docs/architecture.rst) actually means in code: the LLM's output here
    can never contain a fact, only a pointer to where a fact already is.
    """

    category: Literal["flights", "hotel", "attractions", "weather", "budget", "unclear"] = Field(
        description="Which part of the trip plan the question is about. 'unclear' if none fit."
    )
    date: Optional[str] = Field(
        default=None,
        description="Only for a weather question about one specific day. Must be one of the "
        "trip's actual forecast dates, given in the task description -- never a guessed or "
        "invented date, and never set for any category other than weather.",
    )
