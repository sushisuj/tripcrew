"""Weather lookup via OpenWeatherMap.

Real data, no stubbing needed here -- OpenWeatherMap's free tier is an
instant signup, no approval gate, unlike flights and hotels.
"""

import os

import requests
from crewai.tools import tool

from tripcrew.schemas import WeatherReport

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"
OPENWEATHER_GEO = "https://api.openweathermap.org/geo/1.0/direct"


def _geocode(city: str) -> tuple[float, float]:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    response = requests.get(
        OPENWEATHER_GEO,
        params={"q": city, "limit": 1, "appid": api_key},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        raise ValueError(f"Could not geocode city: {city}")
    return results[0]["lat"], results[0]["lon"]


@tool("Weather Lookup")
def get_weather(city: str, date: str) -> WeatherReport:
    """Look up the forecast for a city on a given date (ISO format, e.g. 2026-09-01).

    Note: OpenWeatherMap's free tier is a 5-day/3-hour forecast, not arbitrary
    future dates -- this will need a fallback (seasonal averages, or just an
    honest "forecast not available yet, here's typical weather for this month")
    once dates are more than 5 days out. Not handled yet -- flagged for the
    error-handling pass, not silently ignored.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENWEATHER_API_KEY not set. This should surface to the agent as "
            "a tool failure to handle, not crash the whole crew."
        )
