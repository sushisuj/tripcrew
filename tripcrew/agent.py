"""Agent role definitions for the sequential crew.

Four roles for now (food research deferred until its tool exists, see
docs/architecture.rst): intake/coordinator owns flights, hotels, and the
clarification loop; itinerary research owns attractions and weather;
consolidation merges everything into a TripPlan with a computed budget;
presentation formats the result for the user.

This file only defines the agents themselves, one builder function per
role. Task chaining and the Process.sequential crew assembly aren't wired
up yet -- that's the next piece.
"""

import os

from crewai import LLM, Agent

from tripcrew.tools.attractions import get_attractions
from tripcrew.tools.budget import estimate_budget  # noqa: F401 -- not a CrewAI tool, called directly
from tripcrew.tools.flights import search_flights
from tripcrew.tools.hotels import search_hotels
from tripcrew.tools.weather import get_weather


def build_llm() -> LLM:
    """Same NVIDIA NIM setup as the code-review-crew project, gotchas already paid for:

    the `openai/` prefix forces LiteLLM's generic OpenAI-compatible path instead
    of matching "meta/..." against Meta's own hosted API and failing auth.
    """
    return LLM(
        model="openai/meta/llama-3.1-8b-instruct",
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def build_intake_agent() -> Agent:
    """Owns logistics: flights, hotels, and asking for what's missing.

    Runs first in the sequence. Nothing else can usefully research an
    itinerary until dates and an origin city are actually settled.
    """
    llm = build_llm()
    return Agent(
        role="Trip Intake Coordinator",
        goal=(
            "Nail down the trip's actual logistics before anyone else starts "
            "researching: origin city, dates, and budget if given, plus "
            "flights and a hotel that fit them. Ask directly for anything "
            "essential that's missing instead of guessing."
        ),
        backstory=(
            "A coordinator who won't let downstream research start on "
            "guessed dates or a made-up origin city. Only reports flights "
            "and a hotel the tools actually returned."
        ),
        tools=[search_flights, search_hotels],
        llm=llm,
        verbose=True,
    )


def build_itinerary_agent() -> Agent:
    """Owns attractions and weather. Runs after intake, using its dates."""
    llm = build_llm()
    return Agent(
        role="Itinerary Researcher",
        goal=(
            "Find attractions worth the traveler's time, and use the weather "
            "forecast to inform how they're sequenced across the trip's days."
        ),
        backstory=(
            "A local-knowledge researcher who checks the forecast before "
            "recommending a day full of outdoor sightseeing."
        ),
        tools=[get_attractions, get_weather],
        llm=llm,
        verbose=True,
    )


def build_consolidation_agent() -> Agent:
    """Merges intake and itinerary output into one TripPlan. No tools of its
    own -- works entirely from what the earlier tasks already produced.
    """
    llm = build_llm()
    return Agent(
        role="Trip Consolidator",
        goal=(
            "Merge the intake and itinerary research into one coherent trip "
            "plan, with a budget total computed from the actual numbers, "
            "never stated from memory."
        ),
        backstory=(
            "A meticulous editor who never lets a total stand unless it's "
            "been added up from the real flight, hotel, and attraction "
            "costs already gathered."
        ),
        llm=llm,
        verbose=True,
    )


def build_presentation_agent() -> Agent:
    """Formats the consolidated plan for the user. No tools, no new facts,
    just turning the TripPlan into something readable.
    """
    llm = build_llm()
    return Agent(
        role="Trip Presenter",
        goal="Turn the consolidated trip plan into a clear, practical write-up for the traveler.",
        backstory=(
            "A writer who presents exactly what's in the plan, no "
            "embellishment, no inventing details the plan doesn't contain."
        ),
        llm=llm,
        verbose=True,
    )
