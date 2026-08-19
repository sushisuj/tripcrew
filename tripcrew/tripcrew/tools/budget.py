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
    """Sum whatever price data actually came back, and say so honestly when it didn't.

    `x or 0` on a missing price used to mean "treat unknown as free," which
    silently understates the total instead of raising or refusing -- the
    same failure mode as trusting an LLM's stated total, just moved into the
    arithmetic instead. estimated_cost_usd on Attraction is None every time
    right now, since OpenTripMap doesn't return cost data (see
    attractions.py), which meant attractions_usd was always 0 and nothing
    ever said so. unpriced_categories exists so that's visible instead of
    silent.
    """
    priced_flights = [f for f in flights[:1] if f.price_usd is not None]  # cheapest/first option only
    flights_total = sum(f.price_usd for f in priced_flights)

    hotel_total = (hotel.price_per_night_usd or 0) * nights if hotel and hotel.price_per_night_usd is not None else 0

    priced_attractions = [a for a in attractions if a.estimated_cost_usd is not None]
    attractions_total = sum(a.estimated_cost_usd for a in priced_attractions)

    unpriced_categories = []
    if flights and not priced_flights:
        unpriced_categories.append("flights")
    if hotel and hotel.price_per_night_usd is None:
        unpriced_categories.append("hotel")
    if attractions and not priced_attractions:
        unpriced_categories.append("attractions")

    budget = Budget(
        flights_usd=flights_total,
        hotel_usd=hotel_total,
        attractions_usd=attractions_total,
        unpriced_categories=unpriced_categories,
    )
    return budget.recompute()
