"""Budget aggregation -- deliberately not an LLM call.

This is the concrete version of the lesson from Constellate's groundedness
bug: don't let a model state a total and trust it, derive the total from
the actual tool outputs. A few lines of arithmetic here is cheaper and more
reliable than asking an agent to "make sure the math is right."

Now a real @tool, not just a plain function called from Python. It used to
be imported into agent.py and never actually called by anything, the
consolidation task had output_pydantic=TripPlan and no tools, so the LLM
was writing Budget.total_usd itself from context. That's the exact thing
this docstring argues against. Wiring it in as a tool means the arithmetic
still happens here, in code, not in the LLM's head, the LLM's only job is
handing over the flight/hotel/attraction data it already has, same shape as
get_weather or get_attractions taking a city name and doing the real work
in code.
"""

from crewai.tools import tool

from tripcrew.schemas import Attraction, Budget, Flight, Hotel


@tool("Budget Estimator")
def estimate_budget(
    flights: list[Flight],
    hotel: Hotel | None,
    attractions: list[Attraction],
    nights: int,
) -> Budget:
    """Compute the trip's budget from actual flight, hotel, and attraction data.

    Call this with the flights, hotel, and attractions already gathered by
    the earlier research, don't add up a total yourself. Sums whatever price
    data actually came back, and says so honestly when it didn't.

    `x or 0` on a missing price used to mean "treat unknown as free," which
    silently understates the total instead of raising or refusing -- the
    same failure mode as trusting an LLM's stated total, just moved into the
    arithmetic instead. estimated_cost_usd on Attraction is None every time
    right now, since Geoapify doesn't return cost data (see
    attractions.py), which meant attractions_usd was always 0 and nothing
    ever said so. unpriced_categories exists so that's visible instead of
    silent.

    Flight pricing takes the genuinely cheapest priced option, not just
    whichever came first in the list -- flights[:1] used to be the actual
    logic here despite a comment claiming "cheapest," which meant the
    budget could (and did) report a pricier flight while a cheaper one sat
    right next to it in the same list.
    """
    # CrewAI hands this function whatever the LLM's tool call JSON deserializes
    # to, plain dicts, not Flight/Hotel/Attraction instances, even though the
    # args_schema built from these type hints describes the nested shape.
    # Confirmed by calling estimate_budget.run() directly and hitting
    # AttributeError on flights[0].price_usd. Coerce explicitly instead of
    # assuming the type hints are enforced for us.
    flights = [f if isinstance(f, Flight) else Flight.model_validate(f) for f in flights]
    hotel = hotel if hotel is None or isinstance(hotel, Hotel) else Hotel.model_validate(hotel)
    attractions = [a if isinstance(a, Attraction) else Attraction.model_validate(a) for a in attractions]

    priced_flights = [f for f in flights if f.price_usd is not None]
    cheapest_flight = min(priced_flights, key=lambda f: f.price_usd) if priced_flights else None
    flights_total = cheapest_flight.price_usd if cheapest_flight is not None else 0

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
