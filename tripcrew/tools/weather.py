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
