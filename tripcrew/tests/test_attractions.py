"""Tests for the attractions notability filter and the widen-radius react
step.

get_attractions() isn't covered anywhere else -- only followup.py and
pdf_export.py have tests so far. These mock requests.get so the actual
notability logic (which condition goes on the first request, when the
unfiltered fallback kicks in) and the radius-widening react (see
WIDE_SEARCH_RADIUS_METERS) are checked without a live Geoapify call.
"""

import os
from unittest.mock import MagicMock, patch

from tripcrew.tools.attractions import SEARCH_RADIUS_METERS, WIDE_SEARCH_RADIUS_METERS, get_attractions


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


def _feature(name, category="tourism.sights"):
    return {"properties": {"name": name, "categories": [category]}}


@patch.dict(os.environ, {}, clear=True)
def test_no_api_key_returns_empty_list_without_a_request():
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        assert get_attractions.func(city="Lisbon") == []
        mock_get.assert_not_called()


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_first_request_is_restricted_to_notable_places():
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([_feature("Belem Tower")])]
        result = get_attractions.func(city="Lisbon")

    places_call = mock_get.call_args_list[1]
    assert places_call.kwargs["params"]["conditions"] == "wiki_and_media"
    assert [a.name for a in result] == ["Belem Tower"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_falls_back_to_unfiltered_search_when_notable_search_is_empty():
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _places_response([]),  # notable-only search: nothing
            _places_response([_feature("Local Park")]),  # unfiltered fallback
        ]
        result = get_attractions.func(city="Smalltown")

    assert mock_get.call_count == 3
    notable_call, fallback_call = mock_get.call_args_list[1], mock_get.call_args_list[2]
    assert notable_call.kwargs["params"]["conditions"] == "wiki_and_media"
    assert "conditions" not in fallback_call.kwargs["params"]
    assert [a.name for a in result] == ["Local Park"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_widens_the_radius_once_when_the_unfiltered_search_is_also_empty():
    # Both the notable-only and unfiltered searches come back empty here --
    # the real gap this closes: previously that meant "no attractions,"
    # full stop. Now there's one more attempt, at a wider radius, before
    # giving up.
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _places_response([]),  # notable-only search: nothing
            _places_response([]),  # unfiltered fallback: still nothing
            _places_response([_feature("Distant Overlook")]),  # widened radius: found something
        ]
        result = get_attractions.func(city="Sparsetown")

    assert mock_get.call_count == 4
    widened_call = mock_get.call_args_list[3]
    assert f"circle:-9.1,38.7,{WIDE_SEARCH_RADIUS_METERS}" == widened_call.kwargs["params"]["filter"]
    assert "conditions" not in widened_call.kwargs["params"]
    assert [a.name for a in result] == ["Distant Overlook"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_normal_radius_searches_use_the_normal_radius_not_the_widened_one():
    # Sanity check that the first two requests still use SEARCH_RADIUS_METERS
    # -- WIDE_SEARCH_RADIUS_METERS should only ever appear on the third call.
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        mock_get.side_effect = [_geocode_response(), _places_response([_feature("Belem Tower")])]
        get_attractions.func(city="Lisbon")

    places_call = mock_get.call_args_list[1]
    assert f"circle:-9.1,38.7,{SEARCH_RADIUS_METERS}" == places_call.kwargs["params"]["filter"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_still_returns_empty_list_if_the_widened_search_is_also_empty():
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _places_response([]),
            _places_response([]),
            _places_response([]),  # widened radius: nothing either, genuinely empty
        ]
        result = get_attractions.func(city="Nowheresville")

    assert mock_get.call_count == 4
    assert result == []


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_unnamed_places_are_dropped():
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _places_response([{"properties": {}}, _feature("Belem Tower")]),
        ]
        result = get_attractions.func(city="Lisbon")

    assert [a.name for a in result] == ["Belem Tower"]


@patch.dict(os.environ, {"GEOAPIFY_API_KEY": "test-key"})
def test_geocoding_failure_returns_empty_list():
    with patch("tripcrew.tools.attractions.requests.get") as mock_get:
        bad_geocode = MagicMock()
        bad_geocode.raise_for_status.return_value = None
        bad_geocode.json.return_value = {"results": []}
        mock_get.side_effect = [bad_geocode]
        assert get_attractions.func(city="Nowhereville") == []
