"""Attraction/POI lookup via OpenTripMap.

Real data. Free tier, no card required, instant key -- same category as
weather, not the flights/hotels problem.
"""

import os

import requests
from crewai.tools import tool

from tripcrew.schemas import Attraction

OPENTRIPMAP_BASE = "https://api.opentripmap.com/0.1/en/places"


class AttractionsUnavailable(Exception):
    """Raised for any condition that means attractions can't be looked up
    right now (geocoding miss, network/HTTP failure). Caught in
    get_attractions itself, same shape as weather.py's WeatherUnavailable.
    """


def _geocode(city: str, api_key: str) -> tuple[float, float]:
    try:
        response = requests.get(
            f"{OPENTRIPMAP_BASE}/geoname",
            params={"name": city, "apikey": api_key},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data["lat"], data["lon"]
    except (requests.RequestException, KeyError) as e:
        raise AttractionsUnavailable(f"Geocoding request failed for {city}: {e}") from e


@tool("Attraction Lookup")
def get_attractions(city: str, limit: int = 5) -> list[Attraction]:
    """Find notable tourist attractions in a city.

    OpenTripMap doesn't return cost data, so estimated_cost_usd is left
    unset here on purpose rather than guessed -- the budget tool should
    treat missing attraction costs as "unknown," not zero.

    Returns an empty list if a real lookup can't be produced right now
    (missing API key, geocoding failure, OpenTripMap request failure). Same
    reasoning as get_weather returning None: an empty list already means
    "not available" in this schema, no new sentinel needed, and the
    itinerary task is told not to invent attractions to fill the gap.
    """
    api_key = os.getenv("OPENTRIPMAP_API_KEY")
    if not api_key:
        return []

    try:
        lat, lon = _geocode(city, api_key)
        response = requests.get(
            f"{OPENTRIPMAP_BASE}/radius",
            params={
                "radius": 10000,
                "lat": lat,
                "lon": lon,
                "rate": 3,
                "format": "json",
                "limit": limit,
                "apikey": api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except (AttractionsUnavailable, requests.RequestException):
        return []

    return [
        Attraction(name=item["name"], city=city, category=item.get("kinds", "").split(",")[0] or None)
        for item in results
        if item.get("name")
    ]
