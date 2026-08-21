"""Answers follow-up questions about a finished trip plan.

Not part of the main planning crew in agent.py -- this is a separate,
on-demand single-task crew, run once per follow-up question instead of
once per whole trip. Its only job is classification: one LLM call reads
the question and TripPlan's actual forecast dates, and picks a
TripQuestionIntent (see schemas.py). answer_trip_question() then builds
the real answer in plain Python, reading straight off TripPlan.

This is the "graph traversal, not a RAG pipeline" design from
docs/architecture.rst, implemented literally: TripPlan is already
structured data, so answering a question about it is a lookup, not
generation. Handing the whole plan to an LLM and asking it to write an
answer would reintroduce the exact hallucination risk the rest of this
project is built to avoid, an LLM could state a detail that sounds
plausible but isn't actually in the plan. Classification carries much
less of that risk: the worst a wrong classification does is answer the
wrong category, or fall through to "unclear," not invent a fact.
"""

from crewai import Agent, Crew, Process, Task

from tripcrew.agent import build_llm
from tripcrew.schemas import TripPlan, TripQuestionIntent


def build_intent_agent() -> Agent:
    llm = build_llm()
    return Agent(
        role="Trip Question Router",
        goal="Figure out which part of an already-finished trip plan a follow-up question is about.",
        backstory=(
            "A precise router, not an answerer. Only ever picks a category and, "
            "for a weather question about one specific day, one of the trip's "
            "real forecast dates -- never invents a date that isn't already in "
            "the plan, and never drafts an answer of its own."
        ),
        llm=llm,
        verbose=True,
    )


def build_intent_task(agent: Agent, trip_plan: TripPlan, question: str) -> Task:
    """question is baked directly into the description as a plain value,
    same reasoning as build_itinerary_task_from_plan in agent.py: there's
    no upstream task to chain context from here, this crew has exactly one
    task.
    """
    if trip_plan.weather:
        weather_dates = "\n".join(f"- {report.date}" for report in trip_plan.weather)
    else:
        weather_dates = "(no weather data available for this trip)"

    return Task(
        description=(
            f"The traveler already has a finished {trip_plan.days}-day trip plan "
            f"to {trip_plan.destination!r}. The trip's actual forecast dates are:\n"
            f"{weather_dates}\n\n"
            f'The traveler is now asking: "{question}"\n\n'
            "Classify what they're asking about: flights, hotel, attractions, "
            "weather, or budget. If it's a weather question about a specific day "
            "('day 2', 'the first day', a weekday name, an actual date), resolve "
            "it to exactly one of the dates listed above and put it in the date "
            "field -- only use a date that's actually listed, leave date empty "
            "rather than guess if it doesn't clearly point to one of them. If the "
            "question doesn't clearly match any of the five categories, use "
            "'unclear' rather than forcing it into one that doesn't fit."
        ),
        expected_output=(
            "A TripQuestionIntent with the right category, and a date only when "
            "confident it's one of the exact dates listed above."
        ),
        agent=agent,
        output_pydantic=TripQuestionIntent,
    )


def build_intent_crew(trip_plan: TripPlan, question: str) -> Crew:
    agent = build_intent_agent()
    task = build_intent_task(agent, trip_plan, question)
    return Crew(agents=[agent], tasks=[task], process=Process.sequential, tracing=False, verbose=True)


def format_answer(trip_plan: TripPlan, intent: TripQuestionIntent) -> str:
    """Pure Python, no LLM involved -- every line here reads a real field
    off trip_plan. Kept separate from answer_trip_question() so it's
    testable without a live LLM call: hand it a TripPlan and a
    TripQuestionIntent directly and check the string back.
    """
    if intent.category == "flights":
        if not trip_plan.flights:
            return "No flight information is available for this trip."
        lines = []
        for flight in trip_plan.flights:
            price = f"${flight.price_usd:,.2f}" if flight.price_usd is not None else "price unknown"
            lines.append(f"- {flight.airline or 'Unknown airline'}: {flight.origin} -> {flight.destination} on {flight.departure_date}, {price}")
        return "Flights for this trip:\n" + "\n".join(lines)

    if intent.category == "hotel":
        if trip_plan.hotel is None:
            return "No hotel information is available for this trip."
        hotel = trip_plan.hotel
        price = f"${hotel.price_per_night_usd:,.2f}/night" if hotel.price_per_night_usd is not None else "price unknown"
        return f"{hotel.name} in {hotel.city}. Check-in {hotel.check_in}, check-out {hotel.check_out}, {price}."

    if intent.category == "attractions":
        if not trip_plan.attractions:
            return "No attractions are available for this trip."
        lines = [
            f"- {attraction.name}" + (f" ({attraction.category})" if attraction.category else "")
            for attraction in trip_plan.attractions
        ]
        return "Attractions for this trip:\n" + "\n".join(lines)

    if intent.category == "weather":
        if not trip_plan.weather:
            return "No weather forecast is available for this trip."
        if intent.date:
            match = next((report for report in trip_plan.weather if report.date == intent.date), None)
            if match:
                return f"Weather for {match.date}: {match.summary}."
            # The date didn't actually match one we have -- fall through to
            # the full list rather than claim a specific day has no data
            # when really the classifier just named a date wrong.
        lines = [f"- {report.date}: {report.summary}" for report in trip_plan.weather]
        return "Weather forecast:\n" + "\n".join(lines)

    if intent.category == "budget":
        budget = trip_plan.budget
        lines = [
            f"- Flights: ${budget.flights_usd:,.2f}",
            f"- Hotel: ${budget.hotel_usd:,.2f}",
            f"- Attractions: ${budget.attractions_usd:,.2f}",
            f"- Total: ${budget.total_usd:,.2f}",
        ]
        if budget.unpriced_categories:
            lines.append(f"- Not included in the total: {', '.join(budget.unpriced_categories)}")
        return "Budget for this trip:\n" + "\n".join(lines)

    return (
        "I can only answer questions about this trip's flights, hotel, "
        "attractions, weather, or budget. Try asking about one of those."
    )


def answer_trip_question(trip_plan: TripPlan, question: str) -> str:
    """One LLM call (classification only) plus a deterministic lookup.
    Returns a plain-language answer built entirely from trip_plan's real
    data -- see format_answer()'s docstring for why the split matters.
    """
    result = build_intent_crew(trip_plan, question).kickoff(inputs={})
    intent = result.pydantic
    if intent is None:
        return (
            "Sorry, I couldn't figure out what you're asking. Try asking about "
            "flights, hotel, attractions, weather, or budget for this trip."
        )
    return format_answer(trip_plan, intent)
