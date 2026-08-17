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
