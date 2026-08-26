"""Weather lookup via OpenWeatherMap.

Real data, no stubbing needed here -- OpenWeatherMap's free tier is an
instant signup, no approval gate, unlike flights and hotels.
"""

import os
from datetime import datetime

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


def _closest_forecast_entry(entries: list[dict], target_date: str) -> tuple[dict, int]:
    """Picks the forecast entry whose date is closest to `target_date` (ISO,
    e.g. 2026-09-01), instead of always taking the first entry (roughly
    "now") regardless of which date was actually requested -- that mismatch
    is why every day of a trip was coming back with the identical forecast.

    Returns (entry, day_gap): day_gap is how many calendar days separate
    the picked entry from target_date. 0 means OpenWeatherMap actually had
    an entry for that exact day; anything higher means target_date fell
    outside the 5-day window the free tier forecasts, and the caller
    (get_weather) uses that to mark the result approximate instead of
    quietly presenting a nearby day's forecast as if it were the real one.
    """
    target = datetime.fromisoformat(target_date).date()
    closest = min(
        entries,
        key=lambda entry: abs(
            (datetime.strptime(entry["dt_txt"], "%Y-%m-%d %H:%M:%S").date() - target).days
        ),
    )
    entry_date = datetime.strptime(closest["dt_txt"], "%Y-%m-%d %H:%M:%S").date()
    day_gap = abs((entry_date - target).days)
    return closest, day_gap


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

    OpenWeatherMap's free tier is a 5-day/3-hour forecast, not arbitrary
    future dates. A date further out than that still gets an answer, the
    closest available entry, rather than nothing, but WeatherReport.is_approximate
    is set so nothing downstream mistakes it for a real forecast of that
    day. A seasonal-average fallback would be the fuller fix; this is the
    honest version of the current one, not a replacement for it.
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

        entry, day_gap = _closest_forecast_entry(data["list"], date)
        summary = f"{entry['weather'][0]['description']}, {entry['main']['temp']}C"
    except (WeatherUnavailable, requests.RequestException, KeyError, IndexError, ValueError):
        return None

    return WeatherReport(city=city, date=date, summary=summary, is_approximate=day_gap > 0)
