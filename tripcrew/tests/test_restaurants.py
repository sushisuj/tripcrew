"""Tests for the restaurant/cafe lookup tool.

Same mocking approach as test_attractions.py: mock requests.get so the
request-building and response-parsing logic is checked without a live
Geoapify call. No notability-fallback tests here, unlike attractions --
get_restaurants() only ever makes at most two Places requests (normal
radius, then a widened one if that came back empty, see
WIDE_SEARCH_RADIUS_METERS), never a notable-first request, see its own
docstring for why that doesn't make sense for food.
"""

import os
from unittest.mock import MagicMock, patch

import requests

from tripcrew.tools.restaurants import SEARCH_RADIUS_METERS, WIDE_SEARCH_RADIUS_METERS, get_restaurants


def _geocode_response():
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"results": [{"lat": 38.7, "lon": -9.1}]}
    return mock


def _places_response(features):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"features": features}
    return mock


def _feature(name, category="catering.restaurant"):
    return {"properties": {"name": name, "categories": [category]}}


@patch.dict(os.environ, {}, clear=True)
def test_no_api_key_returns_empty_list_without_a_request():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        assert get_restaurants.func(city="Lisbon") == []
        mock_get.assert_not_called()


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_request_filters_on_restaurant_categories_with_no_notability_condition():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([_feature("Cervejaria Ramiro")])]
        result = get_restaurants.func(city="Lisbon")

    places_call = mock_get.call_args_list[1]
    assert places_call.kwargs["params"]["categories"] == "catering.restaurant,catering.cafe,catering.fast_food"
    assert "conditions" not in places_call.kwargs["params"]
    assert mock_get.call_count == 2
    assert [r.name for r in result] == ["Cervejaria Ramiro"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_no_notability_fallback_request_when_the_places_search_comes_back_empty():
    # Unlike get_attractions, there's no notability-condition fallback to
    # make -- an empty category-filtered result at the normal radius goes
    # straight to the radius-widening react instead (see the next test).
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([]), _places_response([])]
        result = get_restaurants.func(city="Smalltown")

    assert mock_get.call_count == 3
    assert result == []


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_normal_radius_search_uses_the_normal_radius():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([_feature("Cervejaria Ramiro")])]
        get_restaurants.func(city="Lisbon")

    places_call = mock_get.call_args_list[1]
    assert f"circle:-9.1,38.7,{SEARCH_RADIUS_METERS}" == places_call.kwargs["params"]["filter"]
    assert mock_get.call_count == 2


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_widens_the_radius_once_when_the_normal_radius_search_is_empty():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _places_response([]),  # normal radius: nothing
            _places_response([_feature("Roadside Diner")]),  # widened radius: found something
        ]
        result = get_restaurants.func(city="Sparsetown")

    assert mock_get.call_count == 3
    widened_call = mock_get.call_args_list[2]
    assert f"circle:-9.1,38.7,{WIDE_SEARCH_RADIUS_METERS}" == widened_call.kwargs["params"]["filter"]
    assert [r.name for r in result] == ["Roadside Diner"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_unnamed_places_are_dropped():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _places_response([{"properties": {}}, _feature("Cervejaria Ramiro")]),
        ]
        result = get_restaurants.func(city="Lisbon")

    assert [r.name for r in result] == ["Cervejaria Ramiro"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_geocoding_failure_returns_empty_list():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        bad_geocode = MagicMock()
        bad_geocode.raise_for_status.return_value = None
        bad_geocode.json.return_value = {"results": []}
        mock_get.side_effect = [bad_geocode]
        assert get_restaurants.func(city="Nowhereville") == []


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_estimated_cost_is_always_unset_not_zero():
    # Geoapify doesn't return price data for catering places, same gap as
    # attractions -- the budget tool needs to see None here, not a silent 0.
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([_feature("Cervejaria Ramiro")])]
        result = get_restaurants.func(city="Lisbon")

    assert result[0].estimated_cost_usd is None


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_a_request_failure_on_the_normal_radius_tier_still_falls_through_to_the_widened_one():
    # Same structural bug as attractions.py's version of this test:
    # get_restaurants() used to wrap both _fetch_places calls in one
    # try/except, so a request failure on the normal-radius call returned
    # [] immediately and never attempted the widened-radius fallback.
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            requests.HTTPError("boom"),
            _places_response([_feature("Cervejaria Ramiro")]),
        ]
        result = get_restaurants.func(city="Lisbon")

    assert mock_get.call_count == 3
    assert [r.name for r in result] == ["Cervejaria Ramiro"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_request_failures_on_both_tiers_still_return_an_empty_list_not_raise():
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), requests.HTTPError("boom"), requests.HTTPError("boom")]
        assert get_restaurants.func(city="Lisbon") == []


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_picks_the_most_specific_category_not_whichever_came_first():
    # The real bug this closes: a real Lisbon run had all ten restaurants
    # come back tagged the generic "catering" instead of the specific
    # subcategory the request actually filtered on.
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        feature = {
            "properties": {
                "name": "Cervejaria Ramiro",
                "categories": ["catering", "catering.restaurant"],
            }
        }
        mock_get.side_effect = [_geocode_response(), _places_response([feature])]
        result = get_restaurants.func(city="Lisbon")

    assert result[0].category == "catering.restaurant"
