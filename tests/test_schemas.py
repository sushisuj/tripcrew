"""Smoke tests for the schema layer.

Small on purpose -- this proves pytest and the package import path are wired
up correctly, not a real test suite yet. Real coverage (tool error handling,
the clarification flow, budget arithmetic against known inputs) comes once
those pieces exist.
"""

from tripcrew.schemas import Attraction, Budget, Flight, Hotel, TripPlan


def test_budget_recompute_sums_the_parts():
    budget = Budget(flights_usd=500, hotel_usd=300, attractions_usd=50)
    budget.recompute()
    assert budget.total_usd == 850


def test_budget_recompute_ignores_a_stale_total():
    # If something upstream (an LLM, a bad merge) sets total_usd directly,
    # recompute() should override it rather than trust it -- that's the
    # whole point of the function.
    budget = Budget(flights_usd=100, hotel_usd=100, attractions_usd=0, total_usd=999999)
    budget.recompute()
    assert budget.total_usd == 200


def test_trip_plan_defaults_to_no_open_questions():
    plan = TripPlan(destination="Paris", days=3)
    assert plan.open_questions == []
    assert plan.flights == []


def test_flight_requires_a_source():
    flight = Flight(
        origin="LHR",
        destination="CDG",
        departure_date="2026-09-01",
        price_usd=200,
        source="mocked",
    )
    assert flight.source == "mocked"
