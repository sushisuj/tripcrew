"""Restaurant/cafe lookup via Geoapify.

Same API, same key, same /v2/places endpoint as attractions.py -- confirmed
against Geoapify's own docs (apidocs.geoapify.com) before writing this, not
assumed from the attractions integration by analogy. The category taxonomy
under "catering" turned out to be real and fairly deep (cuisine-specific
subcategories like catering.restaurant.italian exist), so a more specific
tool could filter by cuisine later without a new integration.

What doesn't carry over from attractions.py: notability. get_attractions()
filters on Geoapify's wiki_and_media condition first, a real Wikipedia/
Wikidata link, because a genuine landmark usually has one. A good
neighborhood restaurant almost never does -- that condition would come back
near-empty for exactly the places worth recommending, and fall through to
the unfiltered list anyway, which defeats the point of having it. Checked
the Places API response shape directly: a place's properties carry name,
address fields, categories, distance, and place_id, nothing Geoapify itself
computes as a quality or popularity signal, and the underlying data source
is OpenStreetMap, not a curated review platform. So get_restaurants() is
honestly a "what's nearby in this category" search, not a "what's good"
search, and its docstring says that rather than implying a curation step
that isn't there.
"""

import os

import requests
from crewai.tools import tool

from tripcrew.schemas import Restaurant

GEOAPIFY_GEOCODE = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES = "https://api.geoapify.com/v2/places"

# Restaurants and cafes, plus fast food since "somewhere quick to eat" is a
# real part of a travel itinerary too. Deliberately not catering.bar or
# catering.pub -- this tool is about where to eat, not where to drink,
# matching what docs/architecture.rst already committed to before this was
# built ("restaurants and cafes").
RESTAURANT_CATEGORIES = "catering.restaurant,catering.cafe,catering.fast_food"

# Same radius attractions.py uses, no reason for food search to cover a
# wider or narrower area than sightseeing search.
SEARCH_RADIUS_METERS = 10000

# Same widen-once react as attractions.py's WIDE_SEARCH_RADIUS_METERS, tried
# only if the normal-radius search comes back empty -- get_restaurants() has
# no notability condition to fall back from, but geography is still worth
# one more try before reporting nothing found. Same value, same reasoning:
# widen once, don't loop chasing a result a destination may genuinely not have.
WIDE_SEARCH_RADIUS_METERS = 25000


class RestaurantsUnavailable(Exception):
    """Raised for any condition that means restaurants can't be looked up
    right now (geocoding miss, network/HTTP failure). Caught in
    get_restaurants itself, same shape as attractions.py's
    AttractionsUnavailable and weather.py's WeatherUnavailable.
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
        raise RestaurantsUnavailable(f"Geocoding request failed for {city}: {e}") from e


def _fetch_places(lat: float, lon: float, api_key: str, limit: int, radius_meters: int = SEARCH_RADIUS_METERS) -> list[dict]:
    """One Places API call. radius_meters defaults to the normal search
    radius; get_restaurants() passes WIDE_SEARCH_RADIUS_METERS explicitly
    for its one widen-and-retry attempt.
    """
    params = {
        "categories": RESTAURANT_CATEGORIES,
        "filter": f"circle:{lon},{lat},{radius_meters}",
        "limit": limit,
        "apiKey": api_key,
    }
    response = requests.get(GEOAPIFY_PLACES, params=params, timeout=10)
    response.raise_for_status()
    # Places API returns a GeoJSON FeatureCollection, not a flat list --
    # the actual fields live under each feature's "properties".
    return response.json()["features"]


@tool("Restaurant Lookup")
def get_restaurants(city: str, limit: int = 5) -> list[Restaurant]:
    """Find restaurants and cafes in a city.

    No quality filter: unlike get_attractions(), there's no notability
    condition applied here, and Geoapify's Places API doesn't carry a
    rating, popularity, or price-level field for catering places any more
    than it does for attractions. This returns what's nearby in the
    restaurant/cafe/fast-food categories, not a curated "best of" list --
    say that plainly rather than presenting it as recommendation-quality,
    the same honesty rule this project applies to mocked flight/hotel data
    and to attractions' own missing cost data.

    estimated_cost_usd is left unset on purpose, same reasoning as
    Attraction: Geoapify doesn't return price data, so the budget tool
    should treat it as unknown, not zero.

    If the normal-radius search comes back empty, this reacts once more by
    widening to WIDE_SEARCH_RADIUS_METERS before reporting nothing found --
    same react step get_attractions() applies to its own last-resort
    unfiltered search, for the same reason: a genuinely empty result
    deserves one more real attempt, not just a pass-through "not available."

    Returns an empty list if a real lookup can't be produced right now
    (missing API key, geocoding failure, Places request failure) or if both
    attempts above still come back empty. Same reasoning as get_attractions
    and get_weather: an empty list already means "not available" in this
    schema, and the itinerary/food task is told not to invent restaurants to
    fill the gap. agent.py's assemble_trip_plan() is what evaluates a
    genuinely empty result and reports it in TripPlan.research_gaps rather
    than letting it pass through silently.
    """
    api_key = os.getenv("GEOAPIFY_API_KEY")
    if not api_key:
        return []

    try:
        lat, lon = _geocode(city, api_key)
        features = _fetch_places(lat, lon, api_key, limit)
        if not features:
            features = _fetch_places(lat, lon, api_key, limit, radius_meters=WIDE_SEARCH_RADIUS_METERS)
    except (RestaurantsUnavailable, requests.RequestException, KeyError):
        return []

    restaurants = []
    for feature in features:
        props = feature.get("properties", {})
        name = props.get("name")
        if not name:
            # Same as attractions.py: plenty of Places results are unnamed
            # POIs, not useful to hand the agent a nameless "restaurant".
            continue
        categories = props.get("categories") or []
        restaurants.append(Restaurant(name=name, city=city, category=categories[0] if categories else None))
    return restaurants
