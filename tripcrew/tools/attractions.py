"""Attraction/POI lookup via OpenTripMap.

Real data. Free tier, no card required, instant key -- same category as
weather, not the flights/hotels problem.
"""

import os

import requests
from crewai.tools import tool

from tripcrew.schemas import Attraction

OPENTRIPMAP_BASE = "https://api.opentripmap.com/0.1/en/places"


def _geocode(city: str, api_key: str) -> tuple[float, float]:
    response = requests.get(
        f"{OPENTRIPMAP_BASE}/geoname",
        params={"name": city, "apikey": api_key},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return data["lat"], data["lon"]
