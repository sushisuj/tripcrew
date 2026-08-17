"""Hotel search -- mocked for the same reason as flights.py. See that file's
docstring; the same Amadeus-sandbox-vs-real-partner-API tradeoff applies here,
same account even, if Amadeus ends up being the real integration.
"""

import random

from crewai.tools import tool

from tripcrew.schemas import Hotel

_MOCK_HOTEL_NAMES = ["Hotel Central", "The Grand Plaza", "Riverside Inn", "City Suites"]

