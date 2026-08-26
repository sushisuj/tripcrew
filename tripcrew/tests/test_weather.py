"""Tests for the weather date-matching logic.

_closest_forecast_entry() is the actual fix for a real bug: every day of a
trip used to come back with the identical forecast because get_weather()
just took OpenWeatherMap's first list entry (roughly "now") regardless of
which date was requested. These tests are the regression coverage that bug
never had -- mocking requests.get the same way test_attractions.py does, so
the matching logic is checked without a live OpenWeatherMap call.
"""

import os
from unittest.mock import MagicMock, patch

from tripcrew.tools.weather import _closest_forecast_entry, get_weather


def _entry(dt_txt, description="clear sky", temp=20.0):
    return {"dt_txt": dt_txt, "weather": [{"description": description}], "main": {"temp": temp}}


def _geocode_response():
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = [{"lat": 38.7, "lon": -9.1}]
    return mock


def _forecast_response(entries):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"list": entries}
    return mock


def test_closest_forecast_entry_picks_the_matching_date_not_the_first_one():
    # Regression test for the actual bug: taking entries[0] regardless of
    # target_date is what made every day of a trip come back identical.
    entries = [
        _entry("2026-08-24 12:00:00", description="light rain"),
        _entry("2026-08-25 12:00:00", description="broken clouds"),
        _entry("2026-08-26 12:00:00", description="clear sky"),
    ]
    picked = _closest_forecast_entry(entries, "2026-08-26")
    assert picked["weather"][0]["description"] == "clear sky"


def test_closest_forecast_entry_falls_back_to_nearest_when_no_exact_match():
    # OpenWeatherMap's free tier only forecasts 5 days out, so a target
    # further than that has no exact entry -- this is the approximation
    # the still-open 5-day TODO in weather.py refers to.
    entries = [
        _entry("2026-08-24 12:00:00", description="light rain"),
        _entry("2026-08-27 12:00:00", description="broken clouds"),
    ]
    picked = _closest_forecast_entry(entries, "2026-08-29")
    assert picked["weather"][0]["description"] == "broken clouds"


def test_closest_forecast_entry_uses_calendar_date_not_time_of_day():
    entries = [_entry("2026-08-24 03:00:00", description="light rain")]
    picked = _closest_forecast_entry(entries, "2026-08-24")
    assert picked["weather"][0]["description"] == "light rain"


@patch.dict(os.environ, {}, clear=True)
def test_get_weather_with_no_api_key_returns_none_without_a_request():
    with patch("tripcrew.tools.weather.requests.get") as mock_get:
        assert get_weather.func(city="Lisbon", date="2026-08-24") is None
        mock_get.assert_not_called()


@patch.dict(os.environ, {"OPENWEATHER_API_KEY": "test-key"})
def test_get_weather_returns_the_report_for_the_matching_day():
    with patch("tripcrew.tools.weather.requests.get") as mock_get:
        mock_get.side_effect = [
            _geocode_response(),
            _forecast_response([
                _entry("2026-08-24 12:00:00", description="light rain", temp=18.5),
                _entry("2026-08-25 12:00:00", description="broken clouds", temp=21.0),
            ]),
        ]
        result = get_weather.func(city="Lisbon", date="2026-08-25")

    assert result.city == "Lisbon"
    assert result.date == "2026-08-25"
    assert "broken clouds" in result.summary
    assert "21.0" in result.summary


@patch.dict(os.environ, {"OPENWEATHER_API_KEY": "test-key"})
def test_get_weather_returns_none_when_geocoding_finds_nothing():
    with patch("tripcrew.tools.weather.requests.get") as mock_get:
        empty_geocode = MagicMock()
        empty_geocode.raise_for_status.return_value = None
        empty_geocode.json.return_value = []
        mock_get.side_effect = [empty_geocode]
        assert get_weather.func(city="Nowhereville", date="2026-08-24") is None


@patch.dict(os.environ, {"OPENWEATHER_API_KEY": "test-key"})
def test_get_weather_returns_none_on_malformed_forecast_response():
    # A response missing the fields get_weather expects (e.g. "list") should
    # degrade to None like any other failure, not raise and take the crew
    # down with it.
    with patch("tripcrew.tools.weather.requests.get") as mock_get:
        bad_forecast = MagicMock()
        bad_forecast.raise_for_status.return_value = None
        bad_forecast.json.return_value = {"unexpected": "shape"}
        mock_get.side_effect = [_geocode_response(), bad_forecast]
        assert get_weather.func(city="Lisbon", date="2026-08-24") is None
