"""Smoke tests for the schema layer.

Small on purpose -- this proves pytest and the package import path are wired
up correctly, not a real test suite yet. Real coverage (tool error handling,
the clarification flow, budget arithmetic against known inputs) comes once
those pieces exist.
"""

from tripcrew.schemas import Attraction, Budget, Flight, Hotel, TripPlan
