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
