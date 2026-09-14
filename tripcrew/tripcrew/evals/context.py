"""Turns a real TripPlan into the "ground truth" context a deepeval
LLMTestCase checks a write-up against.

deepeval's faithfulness/hallucination metrics take context as a list of
independent claims, not one blob of prose -- confirmed by reading their
docstrings and examples in deepeval's own source, each context entry is
scored against the actual_output separately. One string per checkable fact
in the plan, the same set of fields this project has been careful about
restating correctly since the corrupted-weather bug (see agent.py's
assemble_trip_plan() docstring): flights, hotel, attractions, restaurants,
weather, and budget.

Kept separate from judge_llm.py so this can be tested without a live judge
call (see tests/evals/test_context.py) -- this module makes no network
calls at all, it's plain formatting.
"""

from tripcrew.schemas import TripPlan


def trip_plan_context(plan: TripPlan) -> list[str]:
    """One string per fact, in the same field order TripPlan itself
    declares them. A plan with nothing in a given field (no flights, no
    hotel, empty attractions) just contributes no entry for it, rather
    than a placeholder "no flights" string -- context here is meant to be
    "what's true," not a full narration of what's missing (that's what
    TripPlan.research_gaps and open_questions are for, and both get their
    own entry below when non-empty, since a write-up claiming a gap
    doesn't exist would be exactly the kind of unfaithful claim this
    exists to catch).
    """
    context = [f"Destination: {plan.destination}. Trip length: {plan.days} days."]

    for flight in plan.flights:
        price = f"${flight.price_usd:,.2f}" if flight.price_usd is not None else "price unknown"
        context.append(
            f"Flight ({flight.source}): {flight.airline or 'unknown airline'}, "
            f"{flight.origin} to {flight.destination} on {flight.departure_date}, {price}."
        )

    if plan.hotel:
        hotel = plan.hotel
        price = f"${hotel.price_per_night_usd:,.2f}/night" if hotel.price_per_night_usd is not None else "price unknown"
        context.append(
            f"Hotel ({hotel.source}): {hotel.name} in {hotel.city}, "
            f"{hotel.check_in} to {hotel.check_out}, {price}."
        )

    for attraction in plan.attractions:
        day = f"day {attraction.day}" if attraction.day is not None else "no confidently assigned day"
        context.append(f"Attraction: {attraction.name} ({attraction.category or 'uncategorized'}), {day}.")

    for restaurant in plan.restaurants:
        day = f"day {restaurant.day}" if restaurant.day is not None else "no confidently assigned day"
        context.append(
            f"Restaurant/cafe (a plain nearby-places result, not a rated or curated list): "
            f"{restaurant.name} ({restaurant.category or 'uncategorized'}), {day}."
        )

    for report in plan.weather:
        note = " (approximate, not an exact forecast for that date)" if report.is_approximate else ""
        context.append(f"Weather for {report.date}: {report.summary}{note}.")

    budget = plan.budget
    context.append(
        f"Budget: flights ${budget.flights_usd:,.2f}, hotel ${budget.hotel_usd:,.2f}, "
        f"attractions ${budget.attractions_usd:,.2f}, restaurants ${budget.restaurants_usd:,.2f}, "
        f"total ${budget.total_usd:,.2f}."
    )
    if budget.unpriced_categories:
        context.append(
            "Not included in that total, no price data was available: "
            + ", ".join(budget.unpriced_categories)
            + "."
        )

    if plan.research_gaps:
        context.append("Research gaps (categories where results came back empty or too thin): " + " ".join(plan.research_gaps))

    return context
