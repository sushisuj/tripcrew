"""Hotel search -- mocked for the same reason as flights.py. See that file's
docstring; the same Amadeus-sandbox-vs-real-partner-API tradeoff applies here,
same account even, if Amadeus ends up being the real integration.
"""

import random

from crewai.tools import tool

from tripcrew.schemas import Hotel

_MOCK_HOTEL_NAMES = ["Hotel Central", "The Grand Plaza", "Riverside Inn", "City Suites"]


@tool("Hotel Search")
def search_hotels(city: str, check_in: str, check_out: str) -> Hotel:
    """Search for a hotel in a city for the given date range.

    Returns a single mocked option for now -- source is always "mocked".
    """
    return Hotel(
        name=random.choice(_MOCK_HOTEL_NAMES),
        city=city,
        check_in=check_in,
        check_out=check_out,
        price_per_night_usd=round(random.uniform(80, 300), 2),
        source="mocked",
    )
