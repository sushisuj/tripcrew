"""The planning agent itself.

Single agent, multiple tools, CrewAI's own tool-calling loop does the
sequencing -- deliberately not a fan-out of specialist agents like the
code-review-crew project. Flights/hotels/weather/attractions are
sequential and interdependent (the hotel choice depends on how the flight
dates land, weather can inform which attractions get suggested), so one
agent reasoning step by step maps to the brief's own language ("decide
which tool to use and in what sequence") more literally than parallel
specialists would.

This is a skeleton: the agent and tools are wired up, but the multi-turn
clarification loop (asking the user for missing info before proceeding)
isn't built yet -- that lives in app.py once it exists for real.
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


def build_planner_agent() -> Agent:
    llm = build_llm()
    return Agent(
        role="Travel Planner",
        goal=(
            "Turn a high-level trip request into a concrete, practical plan by "
            "deciding which tools to call and in what order, then evaluating "
            "what they return before answering."
        ),
        backstory=(
            "An experienced trip planner who never invents a flight, hotel, or "
            "price -- only reports what the tools actually returned, and asks "
            "the traveler directly when something essential (origin city, "
            "dates, budget) is missing instead of guessing."
        ),
        tools=[search_flights, search_hotels, get_weather, get_attractions],
        llm=llm,
        verbose=True,
    )
