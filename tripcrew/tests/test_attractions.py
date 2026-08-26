"""Tests for the attractions notability filter.

get_attractions() isn't covered anywhere else -- only followup.py and
pdf_export.py have tests so far. These mock requests.get so the actual
notability logic (which condition goes on the first request, when the
unfiltered fallback kicks in) is checked without a live Geoapify call.
"""

import os
from unittest.mock import MagicMock, patch

from tripcrew.tools.attractions import get_attractions


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
