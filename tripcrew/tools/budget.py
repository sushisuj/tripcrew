"""Budget aggregation -- deliberately not an LLM call.

This is the concrete version of the lesson from Constellate's groundedness
bug: don't let a model state a total and trust it, derive the total from
the actual tool outputs. A few lines of arithmetic here is cheaper and more
reliable than asking an agent to "make sure the math is right."
"""

from tripcrew.schemas import Attraction, Budget, Flight, Hotel
