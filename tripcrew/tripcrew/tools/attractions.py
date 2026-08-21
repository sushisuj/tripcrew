"""Attraction/POI lookup via Geoapify.

Switched from OpenTripMap: free tier compared live against Foursquare and
Overpass/OSM before picking Geoapify -- 3,000 credits/day, no card
required, same instant-signup category as weather. Confirmed request/
response shapes against Geoapify's own docs (apidocs.geoapify.com), not
assumed from the playground example, which itself looked like it was using
a shared public demo key.
"""

import os

import requests
from crewai.tools import tool

from tripcrew.schemas import Attraction

GEOAPIFY_GEOCODE = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES = "https://api.geoapify.com/v2/places"

# Broad but still "worth visiting" -- sights/landmarks, museums and other
# culture venues, and parks. Each of these is a parent category in
# Geoapify's dot-notation scheme, so it already covers its own
# subcategories (tourism.sights.castle, entertainment.culture.gallery,
# etc.) without listing every leaf explicitly.
ATTRACTION_CATEGORIES = "tourism.attraction,tourism.sights,entertainment.museum,entertainment.culture,leisure.park"

# How far out from the city center to search. Matches the radius the old
# OpenTripMap integration used.
SEARCH_RADIUS_METERS = 10000


class AttractionsUnavailable(Exception):
    """Raised for any condition that means attractions can't be looked up
    right now (geocoding miss, network/HTTP failure). Caught in
    get_attractions itself, same shape as weather.py's WeatherUnavailable.
    """


def _geocode(city: str, api_key: str) -> tuple[float, float]:
    try:
        response = requests.get(
            GEOAPIFY_GEOCODE,
            params={"text": city, "type": "city", "limit": 1, "format": "json", "apiKey": api_key},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()["results"]
        return results[0]["lat"], results[0]["lon"]
    except (requests.RequestException, KeyError, IndexError) as e:
        raise AttractionsUnavailable(f"Geocoding request failed for {city}: {e}") from e


@tool("Attraction Lookup")
def get_attractions(city: str, limit: int = 5) -> list[Attraction]:
    """Find notable tourist attractions in a city.

    Geoapify's Places API doesn't return cost data, same gap OpenTripMap
    had, so estimated_cost_usd is left unset here on purpose rather than
    guessed -- the budget tool should treat missing attraction costs as
    "unknown," not zero.

    Returns an empty list if a real lookup can't be produced right now
    (missing API key, geocoding failure, Places request failure). Same
    reasoning as get_weather returning None: an empty list already means
    "not available" in this schema, no new sentinel needed, and the
    itinerary task is told not to invent attractions to fill the gap.
    """
    api_key = os.getenv("GEOAPIFY_API_KEY")
    if not api_key:
        return []

    try:
        lat, lon = _geocode(city, api_key)
        response = requests.get(
            GEOAPIFY_PLACES,
            params={
                "categories": ATTRACTION_CATEGORIES,
                "filter": f"circle:{lon},{lat},{SEARCH_RADIUS_METERS}",
                "limit": limit,
                "apiKey": api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        # Places API returns a GeoJSON FeatureCollection, not a flat list --
        # the actual fields live under each feature's "properties".
        features = response.json()["features"]
    except (AttractionsUnavailable, requests.RequestException, KeyError):
        return []

    attractions = []
    for feature in features:
        props = feature.get("properties", {})
        name = props.get("name")
        if not name:
            # Plenty of Places results are unnamed POIs (a bench, a gate) --
            # not useful to hand the itinerary agent a nameless "attraction".
            continue
        categories = props.get("categories") or []
        attractions.append(Attraction(name=name, city=city, category=categories[0] if categories else None))
    return attractions
