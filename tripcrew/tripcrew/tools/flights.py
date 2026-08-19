"""Flight search -- currently mocked, matching the shape a real integration will need.

Deliberately stubbed rather than skipped. See docs/architecture.rst for the
reasoning: real live-price APIs (Skyscanner, Kiwi) gate access behind a
business-partner approval process that doesn't clear on this timeline.
Amadeus's self-service sandbox is the realistic path forward, but its free
tier returns test data, not live prices, so even a "real" integration here
won't be live pricing -- worth being upfront about that in the writeup
rather than implying otherwise.

The function signature and return type are written as if this already hit
a real API, so swapping the body for an Amadeus call later doesn't require
touching anything that calls this tool.
"""

import random

from crewai.tools import tool

from tripcrew.schemas import Flight

_MOCK_AIRLINES = ["Air France", "British Airways", "Lufthansa", "KLM"]


@tool("Flight Search")
def search_flights(origin: str, destination: str, departure_date: str) -> list[Flight]:
    """Search for flights between two cities on a given date.

    Returns mocked options for now -- source is always "mocked" so nothing
    downstream can mistake this for real pricing.
    """
    return [
        Flight(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            airline=random.choice(_MOCK_AIRLINES),
            price_usd=round(random.uniform(250, 900), 2),
            source="mocked",
        )
        for _ in range(3)
    ]
