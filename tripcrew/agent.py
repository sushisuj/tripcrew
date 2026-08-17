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
