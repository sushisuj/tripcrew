"""Tests for trip_plan_context() -- pure formatting, no network call, so
this runs in the normal `pytest` suite unlike the eval-marked tests under
this same directory (see test_writeup_groundedness.py).
"""

from tripcrew.evals.context import trip_plan_context
from tripcrew.schemas import Attraction, Budget, Flight, Hotel, Restaurant, TripPlan, WeatherReport


def _lisbon_plan(**overrides) -> TripPlan:
    defaults = dict(destination="Lisbon", days=3)
    defaults.update(overrides)
    return TripPlan(**defaults)


def test_a_minimal_plan_still_gets_a_destination_and_budget_line():
    # Nothing else populated -- context should degrade gracefully, not
    # raise or produce an empty list, the same "always something concrete"
    # instinct as _trip_date_range() in agent.py.
    context = trip_plan_context(_lisbon_plan())
    assert any("Destination: Lisbon" in line and "3 days" in line for line in context)
    assert any(line.startswith("Budget:") for line in context)
    assert not any(line.startswith("Flight") for line in context)
    assert not any(line.startswith("Hotel") for line in context)


def test_flight_and_hotel_lines_include_the_source_field():
    # source is the one honesty field this project insists on for
    # flights/hotels (CLAUDE.md's own convention bullet) -- a write-up
    # claiming a live price when the plan says "mocked" should be
    # catchable against context, so it has to actually be in there.
    plan = _lisbon_plan(
        flights=[
            Flight(
                origin="JFK",
                destination="LIS",
                departure_date="2026-09-01",
                airline="Air France",
                price_usd=544.67,
                source="mocked",
            )
        ],
        hotel=Hotel(
            name="Hotel Central",
            city="Lisbon",
            check_in="2026-09-01",
            check_out="2026-09-04",
            price_per_night_usd=203.90,
            source="mocked",
        ),
    )
    context = trip_plan_context(plan)
    assert any("Flight (mocked): Air France, JFK to LIS on 2026-09-01, $544.67." == line for line in context)
    assert any("Hotel (mocked): Hotel Central in Lisbon, 2026-09-01 to 2026-09-04, $203.90/night." == line for line in context)


def test_attraction_and_restaurant_lines_include_day_when_set_and_say_so_when_not():
    plan = _lisbon_plan(
        attractions=[
            Attraction(name="Belem Tower", city="Lisbon", category="tourism.sights", day=1),
            Attraction(name="Unplaced Spot", city="Lisbon"),
        ],
        restaurants=[Restaurant(name="Cervejaria Ramiro", city="Lisbon", category="catering.restaurant", day=2)],
    )
    context = trip_plan_context(plan)
    assert "Attraction: Belem Tower (tourism.sights), day 1." in context
    assert "Attraction: Unplaced Spot (uncategorized), no confidently assigned day." in context
    restaurant_lines = [line for line in context if line.startswith("Restaurant/cafe")]
    assert len(restaurant_lines) == 1
    assert "Cervejaria Ramiro" in restaurant_lines[0]
    assert "day 2" in restaurant_lines[0]
    assert "not a rated or curated list" in restaurant_lines[0]


def test_approximate_weather_is_flagged_in_its_own_context_line():
    plan = _lisbon_plan(
        weather=[
            WeatherReport(city="Lisbon", date="2026-09-01", summary="Light rain, 20C"),
            WeatherReport(city="Lisbon", date="2026-09-10", summary="Clear sky, 22C", is_approximate=True),
        ]
    )
    context = trip_plan_context(plan)
    assert "Weather for 2026-09-01: Light rain, 20C." in context
    assert any(line.startswith("Weather for 2026-09-10:") and "approximate" in line for line in context)


def test_unpriced_categories_get_their_own_context_line_when_present():
    plan = _lisbon_plan(
        budget=Budget(flights_usd=500, hotel_usd=300, attractions_usd=0, unpriced_categories=["attractions"]).recompute()
    )
    context = trip_plan_context(plan)
    assert any(line.startswith("Not included in that total") and "attractions" in line for line in context)


def test_unpriced_categories_line_is_absent_when_theres_nothing_unpriced():
    plan = _lisbon_plan(budget=Budget(flights_usd=500, hotel_usd=300).recompute())
    context = trip_plan_context(plan)
    assert not any(line.startswith("Not included in that total") for line in context)


def test_research_gaps_get_their_own_context_line_when_present():
    plan = _lisbon_plan(research_gaps=["Attractions: no results found for Lisbon, even after widening the search."])
    context = trip_plan_context(plan)
    assert any(line.startswith("Research gaps") and "Attractions" in line for line in context)


def test_research_gaps_line_is_absent_when_theres_nothing_flagged():
    context = trip_plan_context(_lisbon_plan())
    assert not any(line.startswith("Research gaps") for line in context)
