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


class WeatherUnavailable(Exception):
    """Raised for any condition that means a real forecast can't be produced
    right now (missing key, geocoding miss, network/HTTP failure). Caught in
    get_weather itself -- this exists so the three call sites that can fail
    (missing key, _geocode, the forecast request) all funnel into one place
    instead of three different exception types the caller has to know about.
    """


def _geocode(city: str) -> tuple[float, float]:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    try:
        response = requests.get(
            OPENWEATHER_GEO,
            params={"q": city, "limit": 1, "appid": api_key},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as e:
        raise WeatherUnavailable(f"Geocoding request failed for {city}: {e}") from e
    if not results:
        raise WeatherUnavailable(f"Could not geocode city: {city}")
    return results[0]["lat"], results[0]["lon"]


@tool("Weather Lookup")
def get_weather(city: str, date: str) -> WeatherReport | None:
    """Look up the forecast for a city on a given date (ISO format, e.g. 2026-09-01).

    Returns None if a real forecast can't be produced right now (missing API
    key, geocoding failure, OpenWeatherMap request failure). None here means
    the same thing an empty attractions list already means elsewhere: "not
    available," not "assume nothing." TripPlan.weather is a list precisely so
    a missing report just means the list stays shorter, not that the whole
    run has to stop. The itinerary and presentation tasks are told to say so
    plainly rather than invent a forecast.

    Note: OpenWeatherMap's free tier is a 5-day/3-hour forecast, not arbitrary
    future dates -- this will need a fallback (seasonal averages, or just an
    honest "forecast not available yet, here's typical weather for this month")
    once dates are more than 5 days out. Not handled yet, still just a TODO
    below, separate from the failure handling this function now does.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return None

    try:
        lat, lon = _geocode(city)
        response = requests.get(
            f"{OPENWEATHER_BASE}/forecast",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        # TODO: match the closest forecast entry to `date` instead of just
        # grabbing the first one. Placeholder for now -- start small.
        first = data["list"][0]
        summary = f"{first['weather'][0]['description']}, {first['main']['temp']}C"
    except (WeatherUnavailable, requests.RequestException, KeyError, IndexError):
        return None

    return WeatherReport(city=city, date=date, summary=summary)
