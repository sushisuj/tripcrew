"""Tests for the restaurant/cafe lookup tool.

Same mocking approach as test_attractions.py: mock requests.get so the
request-building and response-parsing logic is checked without a live
Geoapify call. No notability-fallback tests here, unlike attractions --
get_restaurants() only ever makes one Places request, see its own
docstring for why a notable-first request doesn't make sense for food.
"""

import os
from unittest.mock import MagicMock, patch

from tripcrew.tools.restaurants import get_restaurants


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
def test_no_fallback_request_when_the_places_search_comes_back_empty():
    # Unlike get_attractions, there's no unfiltered-fallback request to
    # make -- an empty category-filtered result just means "not available".
    with patch("tripcrew.tools.restaurants.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([])]
        result = get_restaurants.func(city="Smalltown")

    assert mock_get.call_count == 2
    assert result == []


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
