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

# Tried once, and only once, if the unfiltered search at SEARCH_RADIUS_METERS
# still comes back empty -- the "react" half of evaluating a tool result
# rather than accepting "nothing found" on the first miss. Real case this
# addresses: a small or sparsely-OSM-tagged destination where 10km genuinely
# doesn't reach enough tagged places, not just a notability gap the
# wiki_and_media fallback already covers. Bounded to a single retry on
# purpose, same reasoning as that fallback: widen once, don't loop trying to
# force a result out of a destination that may just not have one.
WIDE_SEARCH_RADIUS_METERS = 25000

# Geoapify condition restricting results to POIs that carry a Wikipedia or
# Wikidata link -- the actual notability signal. A category match alone
# isn't one: Geoapify's circle search doesn't respect municipality
# boundaries, so "tourism.sights within 10km of Lisbon" can just as easily
# surface a minor, unremarkable spot in Trafaria (a separate town across
# the river) as a landmark in Lisbon itself. That's the real bug this
# fixes, not a hypothetical -- it's what came back on the Lisbon run this
# filter was built to address.
NOTABILITY_CONDITION = "wiki_and_media"


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


def _fetch_places(
    lat: float,
    lon: float,
    api_key: str,
    limit: int,
    notable_only: bool,
    radius_meters: int = SEARCH_RADIUS_METERS,
) -> list[dict]:
    """One Places API call. Split out so get_attractions can call it up to
    three times (notable-only, an unfiltered fallback, then an unfiltered
    search widened to WIDE_SEARCH_RADIUS_METERS) without duplicating the
    request-building logic between them. radius_meters defaults to the
    normal search radius so the first two calls don't need to pass it.
    """
    params = {
        "categories": ATTRACTION_CATEGORIES,
        "filter": f"circle:{lon},{lat},{radius_meters}",
        "limit": limit,
        "apiKey": api_key,
    }
    if notable_only:
        params["conditions"] = NOTABILITY_CONDITION
    response = requests.get(GEOAPIFY_PLACES, params=params, timeout=10)
    response.raise_for_status()
    # Places API returns a GeoJSON FeatureCollection, not a flat list --
    # the actual fields live under each feature's "properties".
    return response.json()["features"]


@tool("Attraction Lookup")
def get_attractions(city: str, limit: int = 5) -> list[Attraction]:
    """Find notable tourist attractions in a city.

    Geoapify's Places API doesn't return cost data, same gap OpenTripMap
    had, so estimated_cost_usd is left unset here on purpose rather than
    guessed -- the budget tool should treat missing attraction costs as
    "unknown," not zero.

    Notability filter: the primary request restricts results to POIs that
    carry a Wikipedia/Wikidata link (see NOTABILITY_CONDITION above), so a
    category match alone doesn't count as "worth visiting" -- that's what
    used to let a wrong-municipality result through. Smaller destinations
    can have thin Wikipedia coverage, so if that comes back empty, this
    falls back to an unfiltered category search rather than reporting zero
    attractions for a real city. Quality-first, not quality-only.

    If even that unfiltered search comes back empty, this reacts once more
    by widening the search to WIDE_SEARCH_RADIUS_METERS before giving up --
    the actual bug that motivated this: a real London run had attractions
    come back empty and nothing downstream reacted to it, the empty list
    just passed straight through to a plan that quietly had no attractions
    in it. Widening geography is a genuine second attempt, not a formality:
    it can turn up real, taggable places outside the normal 10km radius for
    a destination where a 10km circle just didn't happen to catch enough of
    them.

    Returns an empty list if a real lookup can't be produced right now
    (missing API key, geocoding failure, Places request failure) or if all
    three attempts above still come back empty. Same reasoning as
    get_weather returning None: an empty list already means "not available"
    in this schema, no new sentinel needed. The itinerary task is told not
    to invent attractions to fill the gap, and agent.py's
    assemble_trip_plan() is what evaluates a genuinely empty result and
    reports it in TripPlan.research_gaps rather than letting it pass
    through silently.
    """
    api_key = os.getenv("GEOAPIFY_API_KEY")
    if not api_key:
        return []

    try:
        lat, lon = _geocode(city, api_key)
        features = _fetch_places(lat, lon, api_key, limit, notable_only=True)
        if not features:
            features = _fetch_places(lat, lon, api_key, limit, notable_only=False)
        if not features:
            features = _fetch_places(
                lat, lon, api_key, limit, notable_only=False, radius_meters=WIDE_SEARCH_RADIUS_METERS
            )
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
