"""Tests for the follow-up chatbot's answer formatting.

Deliberately not testing build_intent_crew()/answer_trip_question() end to
end -- that needs a live LLM call. format_answer() is where the actual
answer text gets built, and it's pure Python (TripPlan + TripQuestionIntent
in, a string out), so it's fully testable without one. The classification
step is trusted the same way the rest of this project trusts CrewAI's
output_pydantic elsewhere: not re-tested here, just used.
"""

from tripcrew.followup import format_answer
from tripcrew.schemas import (
    Attraction,
    Budget,
    Flight,
    Hotel,
    Restaurant,
    TripPlan,
    TripQuestionIntent,
    WeatherReport,
)


def _trip_plan(**overrides) -> TripPlan:
    defaults = dict(destination="Lisbon", days=4)
    defaults.update(overrides)
    return TripPlan(**defaults)


def test_flights_question_lists_real_flight_data():
    plan = _trip_plan(
        flights=[
            Flight(origin="JFK", destination="LIS", departure_date="2026-08-24", airline="Air France", price_usd=544.67, source="mocked"),
        ]
    )
    answer = format_answer(plan, TripQuestionIntent(category="flights"))
    assert "Air France" in answer
    assert "544.67" in answer
    assert "2026-08-24" in answer


def test_flights_question_with_no_flights_says_so_plainly():
    plan = _trip_plan()
    answer = format_answer(plan, TripQuestionIntent(category="flights"))
    assert "No flight information" in answer


def test_hotel_question_reads_real_hotel_fields():
    plan = _trip_plan(
        hotel=Hotel(name="Hotel Central", city="Lisbon", check_in="2026-08-24", check_out="2026-08-28", price_per_night_usd=203.90, source="mocked")
    )
    answer = format_answer(plan, TripQuestionIntent(category="hotel"))
    assert "Hotel Central" in answer
    assert "2026-08-24" in answer and "2026-08-28" in answer
    assert "203.90" in answer


def test_hotel_question_with_no_hotel_says_so_plainly():
    plan = _trip_plan()
    answer = format_answer(plan, TripQuestionIntent(category="hotel"))
    assert "No hotel information" in answer


def test_attractions_question_lists_names_and_categories():
    plan = _trip_plan(attractions=[Attraction(name="Belem Tower", city="Lisbon", category="tourism.sights")])
    answer = format_answer(plan, TripQuestionIntent(category="attractions"))
    assert "Belem Tower" in answer
    assert "tourism.sights" in answer


def test_attractions_question_shows_day_when_set():
    plan = _trip_plan(
        attractions=[
            Attraction(name="Belem Tower", city="Lisbon", category="tourism.sights", day=2),
            Attraction(name="Unplaced Spot", city="Lisbon"),
        ]
    )
    answer = format_answer(plan, TripQuestionIntent(category="attractions"))
    assert "Day 2: Belem Tower" in answer
    assert "Unplaced Spot" in answer
    # The unplaced one shouldn't get a fabricated day label.
    assert "Day None" not in answer


def test_restaurants_question_lists_names_and_categories():
    plan = _trip_plan(restaurants=[Restaurant(name="Cervejaria Ramiro", city="Lisbon", category="catering.restaurant")])
    answer = format_answer(plan, TripQuestionIntent(category="restaurants"))
    assert "Cervejaria Ramiro" in answer
    assert "catering.restaurant" in answer


def test_restaurants_question_shows_day_when_set():
    plan = _trip_plan(restaurants=[Restaurant(name="Cervejaria Ramiro", city="Lisbon", day=1)])
    answer = format_answer(plan, TripQuestionIntent(category="restaurants"))
    assert "Day 1: Cervejaria Ramiro" in answer


def test_restaurants_question_says_plainly_this_is_not_a_rated_list():
    # The whole point of restaurants.py's own honesty note: don't let the
    # answer imply curation or ratings the tool never provided.
    plan = _trip_plan(restaurants=[Restaurant(name="Cervejaria Ramiro", city="Lisbon")])
    answer = format_answer(plan, TripQuestionIntent(category="restaurants"))
    assert "not a rated or curated list" in answer.lower()


def test_restaurants_question_with_no_restaurants_says_so_plainly():
    plan = _trip_plan()
    answer = format_answer(plan, TripQuestionIntent(category="restaurants"))
    assert "No restaurants are available" in answer


def test_weather_question_for_a_specific_date_returns_only_that_day():
    plan = _trip_plan(
        weather=[
            WeatherReport(city="Lisbon", date="2026-08-24", summary="Light rain, 20C"),
            WeatherReport(city="Lisbon", date="2026-08-25", summary="Broken clouds, 20C"),
        ]
    )
    answer = format_answer(plan, TripQuestionIntent(category="weather", date="2026-08-25"))
    assert "Broken clouds" in answer
    assert "Light rain" not in answer


def test_weather_question_with_unmatched_date_falls_back_to_full_forecast():
    # The classifier naming a date that isn't actually in trip_plan.weather
    # is a real possible failure mode -- falling back to the full list is
    # safer than silently claiming that day has no data.
    plan = _trip_plan(weather=[WeatherReport(city="Lisbon", date="2026-08-24", summary="Light rain, 20C")])
    answer = format_answer(plan, TripQuestionIntent(category="weather", date="2026-09-01"))
    assert "2026-08-24" in answer
    assert "Light rain" in answer


def test_weather_question_for_an_approximate_day_says_so():
    plan = _trip_plan(
        weather=[
            WeatherReport(city="Lisbon", date="2026-08-24", summary="Light rain, 20C"),
            WeatherReport(city="Lisbon", date="2026-09-01", summary="Broken clouds, 20C", is_approximate=True),
        ]
    )
    answer = format_answer(plan, TripQuestionIntent(category="weather", date="2026-09-01"))
    assert "Broken clouds" in answer
    assert "approximate" in answer.lower()


def test_weather_question_with_no_date_returns_full_forecast():
    plan = _trip_plan(
        weather=[
            WeatherReport(city="Lisbon", date="2026-08-24", summary="Light rain, 20C"),
            WeatherReport(city="Lisbon", date="2026-08-25", summary="Broken clouds, 20C"),
        ]
    )
    answer = format_answer(plan, TripQuestionIntent(category="weather"))
    assert "Light rain" in answer and "Broken clouds" in answer


def test_budget_question_reads_real_totals_and_flags_unpriced_categories():
    plan = _trip_plan(budget=Budget(flights_usd=544.67, hotel_usd=815.60, attractions_usd=0, unpriced_categories=["attractions"]).recompute())
    answer = format_answer(plan, TripQuestionIntent(category="budget"))
    assert "544.67" in answer
    assert "1,360.27" in answer
    assert "attractions" in answer.lower()


def test_unclear_category_gives_an_honest_fallback_not_a_guess():
    plan = _trip_plan()
    answer = format_answer(plan, TripQuestionIntent(category="unclear"))
    assert "flights" in answer.lower() and "budget" in answer.lower()
