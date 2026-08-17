"""Budget aggregation -- deliberately not an LLM call.

This is the concrete version of the lesson from Constellate's groundedness
bug: don't let a model state a total and trust it, derive the total from
the actual tool outputs. A few lines of arithmetic here is cheaper and more
reliable than asking an agent to "make sure the math is right."
"""

from tripcrew.schemas import Attraction, Budget, Flight, Hotel


def estimate_budget(
    flights: list[Flight],
    hotel: Hotel | None,
    attractions: list[Attraction],
    nights: int,
) -> Budget:
    flights_total = sum(f.price_usd or 0 for f in flights[:1])  # cheapest/first option only
    hotel_total = (hotel.price_per_night_usd or 0) * nights if hotel else 0
    attractions_total = sum(a.estimated_cost_usd or 0 for a in attractions)

    budget = Budget(
        flights_usd=flights_total,
        hotel_usd=hotel_total,
        attractions_usd=attractions_total,
    )
    return budget.recompute()
