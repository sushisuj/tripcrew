"""Agent role definitions for the sequential crew.

Five roles: intake/coordinator owns flights, hotels, and the clarification
loop; itinerary research owns attractions and weather; food research owns
restaurants and cafes; consolidation merges everything into a TripPlan with
a computed budget; presentation formats the result for the user.

This file defines the agents, their chained tasks, and the Crew that runs
them under Process.sequential. Sequential over hierarchical is deliberate,
see docs/architecture.rst: a manager agent dynamically delegating adds a
second unreliable decision on top of per-task reliability problems already
documented on the code-review-crew project. A fixed, predictable pipeline
is easier to debug when a task's output is wrong.
"""

import os
from datetime import date, timedelta
from typing import Callable

import crewai.llms.cache as _crewai_cache
from crewai import LLM, Agent, Crew, Process, Task
from crewai.crews.crew_output import CrewOutput
from crewai.tasks.task_output import TaskOutput

from tripcrew.schemas import FoodResearch, ItineraryResearch, TripPlan
from tripcrew.tools.attractions import get_attractions
from tripcrew.tools.budget import estimate_budget
from tripcrew.tools.flights import search_flights
from tripcrew.tools.hotels import search_hotels
from tripcrew.tools.restaurants import get_restaurants
from tripcrew.tools.weather import get_weather

# CrewAI (as of 1.15.x) unconditionally tags every message with a
# cache_breakpoint flag meant only for Anthropic's prompt-caching API, then
# sends that same flag to whatever provider is actually configured. Some
# OpenAI-compatible endpoints validate message schemas strictly and reject
# the unrecognized field outright (confirmed on Groq: "property
# 'cache_breakpoint' is unsupported"); others may just ignore it silently,
# NVIDIA NIM's tolerance for it hasn't been confirmed either way. Known
# upstream bug, github.com/crewAIInc/crewAI/issues/5886, fix PRs open but
# not merged as of this writing. This is the workaround from that issue:
# replace the tagging function with a no-op. Harmless to leave in place
# regardless of provider, it just means cache_breakpoint never gets added;
# only remove it if this project ever switches to an Anthropic model where
# that flag is actually meant to work.
_crewai_cache.mark_cache_breakpoint = lambda msg: msg


def build_llm() -> LLM:
    """Switched back from Groq to NVIDIA NIM, this time on Nemotron 3 Ultra
    (550B total params, ~55B active, MoE) instead of the small Llama model
    the project started on. Groq's free tier kept rate-limiting mid-run
    even after cutting the redundant intake call (see build_crew()'s
    intake_plan parameter), 8000 tokens/minute doesn't stretch far across
    a multi-agent pipeline.

    The `openai/` prefix isn't optional here, same gotcha as the original
    NVIDIA setup: it forces LiteLLM's generic OpenAI-compatible path
    instead of matching "nvidia/..." against some other registered
    provider and failing auth. Model ID confirmed against NVIDIA's own
    docs (build.nvidia.com), not assumed from memory.
    """
    return LLM(
        model="openai/nvidia/nemotron-3-ultra-550b-a55b",
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def build_intake_agent() -> Agent:
    """Owns logistics: flights, hotels, and asking for what's missing.

    Runs first in the sequence. Nothing else can usefully research an
    itinerary until dates and an origin city are actually settled.
    """
    llm = build_llm()
    return Agent(
        role="Trip Intake Coordinator",
        goal=(
            "Nail down the trip's actual logistics before anyone else starts "
            "researching: origin city, dates, and budget if given, plus "
            "flights and a hotel that fit them. Ask directly for anything "
            "essential that's missing instead of guessing."
        ),
        backstory=(
            "A coordinator who won't let downstream research start on "
            "guessed dates or a made-up origin city. Only reports flights "
            "and a hotel the tools actually returned."
        ),
        tools=[search_flights, search_hotels],
        llm=llm,
        verbose=True,
    )


def build_itinerary_agent() -> Agent:
    """Owns attractions and weather. Runs after intake, using its dates."""
    llm = build_llm()
    return Agent(
        role="Itinerary Researcher",
        goal=(
            "Find attractions worth the traveler's time, and use the weather "
            "forecast to inform how they're sequenced across the trip's days."
        ),
        backstory=(
            "A local-knowledge researcher who checks the forecast before "
            "recommending a day full of outdoor sightseeing."
        ),
        tools=[get_attractions, get_weather],
        llm=llm,
        verbose=True,
    )


def build_food_agent() -> Agent:
    """Owns restaurants and cafes. Runs after intake, using its dates, same
    shape as the itinerary agent, but doesn't touch attractions/weather --
    was the fifth role docs/architecture.rst described from the start,
    deferred until get_restaurants() existed.

    get_restaurants() has no notability or quality filter, unlike
    get_attractions() (see restaurants.py's own docstring for why that
    doesn't translate to food), so this agent's goal is worded around
    "what's nearby," not "what's best."
    """
    llm = build_llm()
    return Agent(
        role="Food Researcher",
        goal="Find restaurants and cafes near the destination for the traveler to consider.",
        backstory=(
            "A local-options scout, not a critic -- reports what the tool "
            "actually found nearby, never claims a place is recommended or "
            "highly rated when the tool didn't say so."
        ),
        tools=[get_restaurants],
        llm=llm,
        verbose=True,
    )


def build_consolidation_agent() -> Agent:
    """Merges intake, itinerary, and food output into one TripPlan.

    Has exactly one tool, estimate_budget, and it's not optional: this agent
    used to have none, which meant it wrote Budget.total_usd itself as part
    of its own output_pydantic response, exactly the "LLM states a derived
    number" failure the rest of this project is built to avoid. Now it has
    to hand the gathered flight/hotel/attraction/restaurant data to a real
    function and use what comes back.
    """
    llm = build_llm()
    return Agent(
        role="Trip Consolidator",
        goal=(
            "Merge the intake, itinerary, and food research into one "
            "coherent trip plan. Call the Budget Estimator tool with the "
            "actual flight, hotel, attraction, and restaurant data to get "
            "the budget, never write a total from memory."
        ),
        backstory=(
            "A meticulous editor who never lets a total stand unless it "
            "came back from the Budget Estimator tool, fed with the real "
            "flight, hotel, attraction, and restaurant costs already "
            "gathered."
        ),
        tools=[estimate_budget],
        llm=llm,
        verbose=True,
    )


def build_presentation_agent() -> Agent:
    """Formats the consolidated plan for the user. No tools, no new facts,
    just turning the TripPlan into something readable.
    """
    llm = build_llm()
    return Agent(
        role="Trip Presenter",
        goal="Turn the consolidated trip plan into a clear, practical write-up for the traveler.",
        backstory=(
            "A writer who presents exactly what's in the plan, no "
            "embellishment, no inventing details the plan doesn't contain."
        ),
        llm=llm,
        verbose=True,
    )


def build_intake_task(agent: Agent) -> Task:
    """Runs first, no context from anything -- it's the start of the chain.

    {request} is filled in from Crew.kickoff(inputs={"request": ...}) --
    this is the only place the traveler's actual message enters the crew.
    Missing this was a real bug: without it, nothing downstream ever knows
    what was actually asked.

    Outputs a TripPlan, the same model consolidation_task produces later,
    but this one is a draft: attractions and weather stay empty here,
    open_questions is the whole point. That field was designed from the
    start for exactly this ("anything the agent needed but didn't have"),
    not a new model bolted on for the clarification loop. app.py checks
    open_questions before deciding whether to run the rest of the crew or
    ask the traveler something first.
    """
    return Task(
        description=(
            "The traveler asked: {request}\n\n"
            "Determine the destination, trip length in days, origin city, "
            "travel dates, and budget if given. If origin city, dates, or "
            "budget are missing, list each one in open_questions instead of "
            "guessing -- don't search for flights or a hotel until you have "
            "enough to do it for real. Once you do, search using your tools "
            "and report exactly what they returned."
        ),
        expected_output=(
            "A TripPlan with destination and days filled in, flights and "
            "hotel filled in if you had enough to search for them, and "
            "open_questions listing anything essential still missing."
        ),
        agent=agent,
        output_pydantic=TripPlan,
    )


def build_itinerary_task(agent: Agent, intake_task: Task) -> Task:
    """Depends on intake_task's output for destination and dates.

    output_pydantic=ItineraryResearch (not left as free text) so
    get_attractions()'s and get_weather()'s real return values survive
    intact to assemble_trip_plan(), instead of only existing as prose the
    consolidation task's LLM has to re-read and restate into its own
    TripPlan.attractions/weather -- that restating step is where a real
    London run picked up a corrupted weather summary. See
    ItineraryResearch's own docstring in schemas.py.

    Also where Attraction.day gets assigned (see that field's docstring):
    this task's own reasoning about which day suits which attraction used
    to only ever reach the traveler as prose in the final write-up, this
    is that same reasoning captured as data instead.
    """
    return Task(
        description=(
            "Using the destination and dates from the intake research, find "
            "attractions worth visiting and check the weather forecast. Use "
            "the forecast to note which days suit outdoor attractions and "
            "which don't. Both tools return an empty result rather than an "
            "error when they can't actually look something up -- treat an "
            "empty result as 'not available for this trip,' don't invent a "
            "plausible-sounding attraction or forecast to fill the gap. If a "
            "weather report is marked approximate, say so plainly (the real "
            "forecast for that day isn't out yet), don't present it as an "
            "exact forecast. Report the attractions and weather exactly as "
            "the tools returned them -- don't reword or summarize a weather "
            "summary string, copy it as given. For each attraction, set "
            "its day to a number from 1 to the trip's total number of days "
            "(from the intake research), sequencing outdoor attractions on "
            "better-weather days where the forecast actually supports that "
            "call. Leave day unset for an attraction if you're not "
            "confident where it fits, an unset day is honest, a guessed "
            "one isn't."
        ),
        expected_output=(
            "The attractions and weather forecast the tools actually "
            "returned, as structured data, empty lists where a tool came "
            "back empty rather than an invented substitute, and a day "
            "assigned to each attraction wherever the forecast gave a real "
            "basis for placing it."
        ),
        agent=agent,
        context=[intake_task],
        output_pydantic=ItineraryResearch,
    )


def _trip_date_range(intake_plan: TripPlan) -> str:
    """Best-effort human-readable date range for the trip, derived from
    whatever real date intake actually gathered: the first flight's
    departure_date, falling back to the hotel's check_in if there's no
    flight yet. Returns a plain sentence instead of raising if neither is
    present, so build_itinerary_task_from_plan always has *something*
    concrete to hand the agent instead of silently omitting dates -- that
    omission was the actual bug (see that function's docstring): with no
    real date in the description, the itinerary/weather agent was free to
    invent one, which is how a Lisbon trip in November came back with
    weather dated the following January.

    Also see build_itinerary_task's own docstring for why this task uses
    output_pydantic=ItineraryResearch rather than free text.
    """
    start_str = None
    if intake_plan.flights and intake_plan.flights[0].departure_date:
        start_str = intake_plan.flights[0].departure_date
    elif intake_plan.hotel and intake_plan.hotel.check_in:
        start_str = intake_plan.hotel.check_in

    if not start_str:
        return (
            "No confirmed travel dates are available yet -- don't invent "
            "any, note that weather isn't available instead."
        )

    try:
        start = date.fromisoformat(start_str)
        end = start + timedelta(days=max(intake_plan.days - 1, 0))
        return f"The trip runs from {start.isoformat()} to {end.isoformat()}."
    except ValueError:
        # Source data wasn't a clean ISO date -- pass it through verbatim
        # rather than crashing the task-building step over a formatting
        # quirk, still far better than supplying no date at all.
        return f"The trip starts on {start_str!r}, use that date as given."


def build_itinerary_task_from_plan(agent: Agent, intake_plan: TripPlan) -> Task:
    """Same job as build_itinerary_task, for the case where intake already
    ran separately (build_intake_crew(), see app.py's two-phase flow) and
    its result is already known. Destination and days are baked directly
    into the description as plain values instead of coming through Task
    context chaining, since there's no intake_task in this crew to chain
    from -- this is what lets build_crew() skip rerunning intake from
    scratch, see its own docstring.

    Also bakes in the real trip date range via _trip_date_range(). This
    used to bake in only destination and days, nothing about dates -- the
    itinerary/weather agent had no real date to anchor to and made one up,
    which is why get_weather() was getting called with hallucinated dates
    months off from the actual trip. Fixed here rather than in
    get_weather() itself, since the tool has no way to know what date it
    *should* have been called with, only what it was given.

    output_pydantic=ItineraryResearch, same reasoning as build_itinerary_task,
    including day assignment on each attraction (see Attraction.day's
    docstring in schemas.py) -- phrased with the real day count baked in
    below instead of "the trip's total number of days" the way
    build_itinerary_task has to phrase it, since this variant already has
    the real value on hand.
    """
    date_range = _trip_date_range(intake_plan)
    return Task(
        description=(
            f"The intake research already determined the destination is "
            f"{intake_plan.destination!r} and the trip is {intake_plan.days} "
            f"days. {date_range} Using this destination and these exact "
            "dates, find attractions worth visiting and check the weather "
            "forecast for the actual trip dates above -- don't check or "
            "report weather for any other date. Use the forecast to note "
            "which days suit outdoor attractions and which don't. Both "
            "tools return an empty result rather than an error when they "
            "can't actually look something up -- treat an empty result as "
            "'not available for this trip,' don't invent a "
            "plausible-sounding attraction or forecast to fill the gap. If a "
            "weather report is marked approximate, say so plainly (the real "
            "forecast for that day isn't out yet), don't present it as an "
            "exact forecast. Report the attractions and weather exactly as "
            "the tools returned them -- don't reword or summarize a weather "
            f"summary string, copy it as given. For each attraction, set its "
            f"day to a number from 1 to {intake_plan.days}, sequencing "
            "outdoor attractions on better-weather days where the forecast "
            "actually supports that call. Leave day unset for an attraction "
            "if you're not confident where it fits, an unset day is honest, "
            "a guessed one isn't."
        ),
        expected_output=(
            "The attractions and weather forecast the tools actually "
            "returned, as structured data, empty lists where a tool came "
            "back empty rather than an invented substitute, and a day "
            "assigned to each attraction wherever the forecast gave a real "
            "basis for placing it."
        ),
        agent=agent,
        output_pydantic=ItineraryResearch,
    )


def build_food_task(agent: Agent, intake_task: Task) -> Task:
    """Depends on intake_task's output for destination, same as
    build_itinerary_task -- food research doesn't need attractions or
    weather, just destination and dates, so it chains from intake directly
    rather than from the itinerary task.

    output_pydantic=FoodResearch for the same reason build_itinerary_task
    has output_pydantic=ItineraryResearch: get_restaurants()'s real return
    value should survive to assemble_trip_plan() untouched, not get
    re-authored by the consolidation task's LLM.

    Also assigns Restaurant.day, same field and same reasoning as
    Attraction.day (schemas.py), but this agent has no weather signal to
    reason from the way the itinerary agent does, so its job is just an
    even spread across the trip's days, not weather-aware sequencing.
    """
    return Task(
        description=(
            "Using the destination and dates from the intake research, find "
            "restaurants and cafes worth listing for the traveler. The "
            "lookup tool returns whatever's nearby in the restaurant/cafe/"
            "fast-food categories, not a curated or rated list -- report "
            "exactly what it returned, don't claim a place is recommended "
            "or highly rated when the tool didn't say so. It returns an "
            "empty result rather than an error when it can't actually look "
            "something up -- treat an empty result as 'not available for "
            "this trip,' don't invent a plausible-sounding restaurant to "
            "fill the gap. Spread the restaurants across the trip's total "
            "number of days (from the intake research) by setting each "
            "one's day to a number from 1 to that total, so the traveler "
            "isn't left with every option dumped on one day. Leave day "
            "unset for a restaurant only if there are too few to spread "
            "sensibly, don't force a day onto something that doesn't need one."
        ),
        expected_output=(
            "The restaurants and cafes the tool actually returned, as "
            "structured data, an empty list rather than an invented "
            "substitute if the tool came back empty, spread across the "
            "trip's days rather than left unassigned."
        ),
        agent=agent,
        context=[intake_task],
        output_pydantic=FoodResearch,
    )


def build_food_task_from_plan(agent: Agent, intake_plan: TripPlan) -> Task:
    """Same job as build_food_task, for the case where intake already ran
    separately (build_intake_crew(), see app.py's two-phase flow). Same
    date-baking approach as build_itinerary_task_from_plan and for the same
    reason: there's no intake_task in this crew to chain context from.

    output_pydantic=FoodResearch, same reasoning as build_food_task,
    including day assignment with the real day count baked in below.
    """
    date_range = _trip_date_range(intake_plan)
    return Task(
        description=(
            f"The intake research already determined the destination is "
            f"{intake_plan.destination!r} and the trip is {intake_plan.days} "
            f"days. {date_range} Using this destination, find restaurants "
            "and cafes worth listing for the traveler. The lookup tool "
            "returns whatever's nearby in the restaurant/cafe/fast-food "
            "categories, not a curated or rated list -- report exactly what "
            "it returned, don't claim a place is recommended or highly "
            "rated when the tool didn't say so. It returns an empty result "
            "rather than an error when it can't actually look something up "
            "-- treat an empty result as 'not available for this trip,' "
            "don't invent a plausible-sounding restaurant to fill the gap. "
            f"Spread the restaurants across the trip's {intake_plan.days} "
            "days by setting each one's day to a number from 1 to "
            f"{intake_plan.days}, so the traveler isn't left with every "
            "option dumped on one day. Leave day unset for a restaurant "
            "only if there are too few to spread sensibly, don't force a "
            "day onto something that doesn't need one."
        ),
        expected_output=(
            "The restaurants and cafes the tool actually returned, as "
            "structured data, an empty list rather than an invented "
            "substitute if the tool came back empty, spread across the "
            "trip's days rather than left unassigned."
        ),
        agent=agent,
        output_pydantic=FoodResearch,
    )


def build_consolidation_task(agent: Agent, intake_task: Task, itinerary_task: Task, food_task: Task) -> Task:
    """Depends on all three prior research tasks. Not the only task with a
    pydantic output type any more (itinerary_task and food_task now have
    their own, see build_itinerary_task and build_food_task), but still the
    one place a full TripPlan actually gets assembled.

    This task's own attractions/weather/restaurants fields are not the
    fields that end up in the final plan: assemble_trip_plan() overwrites
    them with itinerary_task's and food_task's own structured output right
    after kickoff, since this agent restating a list it already has in
    context is exactly the kind of re-authoring that corrupted a weather
    summary in a real run (see ItineraryResearch's docstring in
    schemas.py). Left un-penalized here on purpose rather than telling the
    agent to skip those fields entirely: an empty attractions list would
    make expected_output harder to satisfy for no benefit, since the real
    values get substituted in regardless of what this task writes.
    """
    return Task(
        description=(
            "Merge the intake, itinerary, and food research into one "
            "TripPlan. Call the Budget Estimator tool with the actual "
            "flights, hotel, attractions, restaurants, and number of nights "
            "from the earlier research, and use exactly what it returns as "
            "the budget. Don't compute or state a total yourself, and don't "
            "change the numbers the tool gives back, including "
            "unpriced_categories."
        ),
        expected_output=(
            "A complete TripPlan with a budget that came from the Budget "
            "Estimator tool, not a total you wrote yourself."
        ),
        agent=agent,
        context=[intake_task, itinerary_task, food_task],
        output_pydantic=TripPlan,
    )


def build_consolidation_task_from_plan(
    agent: Agent, intake_plan: TripPlan, itinerary_task: Task, food_task: Task
) -> Task:
    """Same job as build_consolidation_task, paired with
    build_itinerary_task_from_plan and build_food_task_from_plan. Needs the
    intake plan's flights and hotel data verbatim to call the Budget
    Estimator tool correctly, so the whole plan gets embedded as JSON
    rather than just destination/days -- unlike the itinerary and food
    tasks, this one can't get away with a short summary. interpolate_only
    (CrewAI's template-filling step, runs on every task description during
    kickoff) only substitutes bare {identifier} placeholders, confirmed by
    reading its source, so the embedded JSON's own braces don't collide
    with it.

    Same caveat as build_consolidation_task: this task's own
    attractions/weather/restaurants output gets overwritten by
    assemble_trip_plan() using itinerary_task's and food_task's real
    structured output, not trusted as-is.
    """
    intake_json = intake_plan.model_dump_json(indent=2)
    return Task(
        description=(
            "The intake research already gathered this data, use it "
            f"exactly as given, don't re-derive or restate it differently:\n\n{intake_json}\n\n"
            "Merge this with the itinerary and food research into one "
            "TripPlan. Call the Budget Estimator tool with the actual "
            "flights, hotel, attractions, restaurants, and number of nights "
            "from the data above and the itinerary/food research, and use "
            "exactly what it returns as the budget. Don't compute or state "
            "a total yourself, and don't change the numbers the tool gives "
            "back, including unpriced_categories."
        ),
        expected_output=(
            "A complete TripPlan with a budget that came from the Budget "
            "Estimator tool, not a total you wrote yourself."
        ),
        agent=agent,
        context=[itinerary_task, food_task],
        output_pydantic=TripPlan,
    )


def build_presentation_task(agent: Agent, consolidation_task: Task) -> Task:
    """Depends on the consolidated TripPlan. Last task in the chain.

    One real limitation worth knowing if this gets touched: this task
    reads the consolidation task's own attractions/weather/restaurants as
    context, the same fields assemble_trip_plan() (agent.py) later
    overwrites with itinerary_task's and food_task's real output, because
    that overwrite only happens after crew.kickoff() returns, this task
    has already run by then. So the write-up's day-by-day structure comes
    from the consolidation task's own (less trustworthy) copy, while the
    PDF's day-by-day tables (pdf_export.py) come from the corrected one
    app.py actually uses. That's not a new gap this task introduces, the
    write-up's sequencing was always the LLM's own retelling rather than
    grounded data, same as the whole reason assemble_trip_plan() exists.
    The write-up is presentation, the PDF's tables are the source of truth.

    Same caveat applies to research_gaps: this task reads the consolidation
    task's own (empty, at this point in the chain) copy of that field, not
    assemble_trip_plan()'s real evaluation, since that evaluation also only
    runs after crew.kickoff() returns. The instruction below tells the
    agent to mention it anyway on the chance a future consolidation
    variant populates it, but app.py's sidebar (render_sidebar()) is the
    reliable place a traveler actually sees research_gaps today, not this
    write-up.
    """
    return Task(
        description=(
            "Turn the consolidated TripPlan into a clear, practical "
            "write-up for the traveler. Present exactly what's in the "
            "plan, don't add details the plan doesn't contain. Restaurants "
            "came from a plain nearby-places lookup, not a rated or "
            "curated list -- present them as options to consider, not as "
            "recommendations. If budget.unpriced_categories isn't empty, "
            "say plainly that the total doesn't include those categories, "
            "don't present it as a complete number. If any weather report "
            "has is_approximate set, say plainly that day's forecast is an "
            "estimate, not a real forecast for that date. Where an "
            "attraction or restaurant has a day set, structure the write-up "
            "around those days (Day 1, Day 2, and so on); if day isn't set "
            "for something, mention it without forcing it onto a day you're "
            "not confident about. If research_gaps isn't empty, mention "
            "each one plainly (for example, say attractions came back empty "
            "for the destination), don't quietly describe whatever's left "
            "as if it were the complete picture."
        ),
        expected_output=(
            "A readable trip plan write-up covering flights, hotel, "
            "attractions, restaurants, weather, and budget, organized by "
            "day wherever the plan's own day fields support that, and "
            "naming any research gap plainly rather than glossing over it."
        ),
        agent=agent,
        context=[consolidation_task],
    )


def build_crew(
    intake_plan: TripPlan | None = None,
    task_callback: Callable[[TaskOutput], None] | None = None,
) -> Crew:
    """Assembles the chained tasks into a Process.sequential Crew. This is
    what app.py should call, not the individual builder functions above --
    those exist mainly so this function and tests can construct pieces
    independently.

    intake_plan is the already-satisfied draft from build_intake_crew()
    (see app.py's two-phase flow: it runs intake alone first, checks
    open_questions, and only calls this function once that draft is
    complete). When it's given, this crew skips intake_task entirely and
    starts from itinerary and food research, with the known destination/
    days/flights/hotel baked into the remaining tasks' descriptions instead
    of coming from a freshly-run intake_task's context. That used to be a
    "known simplification" (rerunning intake from scratch, one redundant
    LLM call every message) -- redundant LLM calls are exactly what burns
    through Groq's free-tier rate limit fastest, so it stopped being a
    minor inefficiency and became a real reason a plan could fail outright.

    Passing no intake_plan keeps the original five-task chain, for tests
    or any caller that doesn't already have a satisfied draft on hand.

    task_callback is Crew's own hook (confirmed via the installed crewai
    source, crew.py/task.py: fires once per task, right after that task
    finishes, called as task_callback(task.output)), not something bolted
    on here. Process.sequential guarantees tasks complete in list order, so
    app.py can count calls against a fixed stage-label list to build a live
    step indicator without CrewAI needing to know anything about Streamlit.
    Not wrapped in a try/except here on purpose -- app.py's callback is
    responsible for not raising, a UI update failing should never be able
    to take the actual crew run down with it.
    """
    itinerary_agent = build_itinerary_agent()
    food_agent = build_food_agent()
    consolidation_agent = build_consolidation_agent()
    presentation_agent = build_presentation_agent()

    if intake_plan is not None:
        itinerary_task = build_itinerary_task_from_plan(itinerary_agent, intake_plan)
        food_task = build_food_task_from_plan(food_agent, intake_plan)
        consolidation_task = build_consolidation_task_from_plan(
            consolidation_agent, intake_plan, itinerary_task, food_task
        )
        presentation_task = build_presentation_task(presentation_agent, consolidation_task)
        return Crew(
            agents=[itinerary_agent, food_agent, consolidation_agent, presentation_agent],
            tasks=[itinerary_task, food_task, consolidation_task, presentation_task],
            process=Process.sequential,
            tracing=False,
            verbose=True,
            task_callback=task_callback,
        )

    intake_agent = build_intake_agent()
    intake_task = build_intake_task(intake_agent)
    itinerary_task = build_itinerary_task(itinerary_agent, intake_task)
    food_task = build_food_task(food_agent, intake_task)
    consolidation_task = build_consolidation_task(consolidation_agent, intake_task, itinerary_task, food_task)
    presentation_task = build_presentation_task(presentation_agent, consolidation_task)

    return Crew(
        agents=[intake_agent, itinerary_agent, food_agent, consolidation_agent, presentation_agent],
        tasks=[intake_task, itinerary_task, food_task, consolidation_task, presentation_task],
        process=Process.sequential,
        tracing=False,
        verbose=True,
        task_callback=task_callback,
    )


def build_intake_crew() -> Crew:
    """A one-task crew running intake alone, for the clarification-gathering
    loop in app.py. Checking open_questions here is cheaper than running
    the full five-agent pipeline just to find out something's missing.

    app.py passes this crew's result straight into build_crew(intake_plan=...)
    once open_questions comes back empty, so intake only ever runs once per
    message, not twice like it used to.
    """
    intake_agent = build_intake_agent()
    intake_task = build_intake_task(intake_agent)
    return Crew(
        agents=[intake_agent],
        tasks=[intake_task],
        process=Process.sequential,
        tracing=False,
        verbose=True,
    )


def assemble_trip_plan(result: CrewOutput) -> TripPlan | None:
    """Pulls the real consolidated TripPlan out of a finished build_crew()
    result, then overwrites its attractions, weather, and restaurants with
    itinerary_task's and food_task's own structured output, verbatim.

    Why this exists: the consolidation task's output_pydantic=TripPlan asks
    its LLM to restate attractions/weather/restaurants as part of authoring
    the whole plan, not just copy them, and an LLM restating a value it
    already has in context is the same failure CLAUDE.md already warns
    about for a Budget.total_usd, just applied to a list of text fields
    instead of a number. Confirmed as a real bug, not a theoretical one: a
    real London PDF came back with the weather summary "Light rain, ~22C
    (approximate) (approximate)", a corruption that only appears in the
    consolidation task's own retelling, get_weather()'s actual tool output
    is clean. itinerary_task and food_task now carry ItineraryResearch and
    FoodResearch as their own output_pydantic (see build_itinerary_task and
    build_food_task), so their pydantic output is the one place those three
    fields are guaranteed to match what the tools actually returned. This
    function is where that guarantee actually gets applied, callers
    (app.py) should use this instead of reading the consolidation task's
    TripPlan directly.

    Finds each task's output by isinstance rather than a fixed list index,
    same reasoning as app.py's own comment on the code this replaces: it
    shouldn't silently break if build_crew()'s task order or count changes.
    Returns None if no TripPlan is found at all, which shouldn't happen in
    normal operation but stays defensive rather than raising, matching the
    prior inline check this replaces.

    Also clamps Attraction.day/Restaurant.day: unlike the rest of what this
    function copies over, day isn't a tool's raw output, it's the
    itinerary/food agent's own reasoning about which day something belongs
    on (see Attraction.day's docstring in schemas.py), so it's a genuinely
    LLM-authored value, not a restated one, no groundedness issue with
    trusting it in principle. But it's still a number the model could get
    wrong the same way it could invent anything else, and TripPlan.days is
    known for certain by this point, so any day outside 1..days gets reset
    to None here rather than shown as, say, "Day 7" on a 3-day trip.

    Also overwrites TripPlan.research_gaps with a fresh evaluation of the
    real, substituted attractions/restaurants/weather (see
    _evaluate_research_gaps()), same reasoning as everything else this
    function overwrites: a count of what's actually in the final lists is a
    checkable fact once those lists are the real ones, not something to
    trust the consolidation task's own guess about.
    """
    consolidated_plan = next(
        (t.pydantic for t in result.tasks_output if isinstance(t.pydantic, TripPlan)),
        None,
    )
    if consolidated_plan is None:
        return None

    itinerary_research = next(
        (t.pydantic for t in result.tasks_output if isinstance(t.pydantic, ItineraryResearch)),
        None,
    )
    if itinerary_research is not None:
        consolidated_plan.attractions = itinerary_research.attractions
        consolidated_plan.weather = itinerary_research.weather

    food_research = next(
        (t.pydantic for t in result.tasks_output if isinstance(t.pydantic, FoodResearch)),
        None,
    )
    if food_research is not None:
        consolidated_plan.restaurants = food_research.restaurants

    _clamp_invalid_days(consolidated_plan.attractions, consolidated_plan.days)
    _clamp_invalid_days(consolidated_plan.restaurants, consolidated_plan.days)

    consolidated_plan.research_gaps = _evaluate_research_gaps(consolidated_plan)

    return consolidated_plan


# Below this count, attractions/restaurants get flagged as a research gap
# even when non-empty. One or two results for a whole trip isn't meaningfully
# different from zero for planning purposes, it just fails silently instead
# of loudly -- the same honesty rule Budget.unpriced_categories applies to a
# price gets applied here to a count. Chosen as a low, deliberately
# conservative bar: this should catch "the tool basically came up empty," not
# flag every small destination that genuinely only has a handful of notable
# places.
THIN_RESEARCH_THRESHOLD = 2


def _evaluate_research_gaps(plan: TripPlan) -> list[str]:
    """The "evaluate" half of reacting to a bad tool result, run once the
    plan's attractions/restaurants/weather are the real, substituted values
    (see assemble_trip_plan(), which calls this after the substitution and
    day-clamping above). The "react" half already happened inside
    get_attractions()/get_restaurants() themselves -- both widen their
    search radius once before giving up, see WIDE_SEARCH_RADIUS_METERS in
    tripcrew/tools/attractions.py and restaurants.py. This is what's left to
    do once that's exhausted and a category is still empty or thin: say so,
    plainly, instead of letting an empty or near-empty list pass silently
    into the write-up and the PDF as if that were the whole story.

    This exists because of a real gap, not a hypothetical one: a London run
    had get_attractions() come back empty (since fixed, see
    NOTABILITY_CONDITION's own docstring for the wrong-municipality bug that
    caused it), and nothing anywhere reacted to that -- the write-up just
    quietly described a London trip with no attractions in it, no different
    in tone from a trip where attractions genuinely weren't asked about.
    TripPlan.research_gaps is what closes that: something a caller (the
    presentation task, app.py's sidebar) can check and actually say out
    loud.

    Weather isn't scored against THIN_RESEARCH_THRESHOLD the way attractions
    and restaurants are -- a handful of forecast entries covering a trip's
    real dates is normal and complete, not thin, so this only checks whether
    the list is empty outright. WeatherReport.is_approximate already carries
    the finer-grained honesty signal for weather, per forecast entry, that
    this function handles as a threshold for the other two.
    """
    gaps = []

    attraction_count = len(plan.attractions)
    if attraction_count < THIN_RESEARCH_THRESHOLD:
        gaps.append(
            f"Attractions: {_gap_phrase(attraction_count)} for {plan.destination}, "
            "even after widening the search."
        )

    restaurant_count = len(plan.restaurants)
    if restaurant_count < THIN_RESEARCH_THRESHOLD:
        gaps.append(
            f"Restaurants: {_gap_phrase(restaurant_count)} for {plan.destination}, "
            "even after widening the search."
        )

    if not plan.weather:
        gaps.append(f"Weather: no forecast could be found for {plan.destination}.")

    return gaps


def _gap_phrase(count: int) -> str:
    """'no results found' for zero, 'only N result(s) found' for a thin but
    non-empty count -- shared wording between the attractions and
    restaurants gap messages in _evaluate_research_gaps() so the two don't
    drift out of sync with each other.
    """
    if count == 0:
        return "no results found"
    return f"only {count} result{'s' if count != 1 else ''} found"


def _clamp_invalid_days(items: list, days: int) -> None:
    """Resets .day to None on any item whose day falls outside 1..days,
    in place. Shared by assemble_trip_plan() for both attractions and
    restaurants, Attraction and Restaurant aren't a common pydantic base
    class, just two models that both happen to carry a `day` field, so
    this takes a plain list and relies on duck typing rather than a shared
    type hint.
    """
    for item in items:
        if item.day is not None and not (1 <= item.day <= days):
            item.day = None
