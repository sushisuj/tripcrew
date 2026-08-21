"""Agent role definitions for the sequential crew.

Four roles for now (food research deferred until its tool exists, see
docs/architecture.rst): intake/coordinator owns flights, hotels, and the
clarification loop; itinerary research owns attractions and weather;
consolidation merges everything into a TripPlan with a computed budget;
presentation formats the result for the user.

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
from crewai.tasks.task_output import TaskOutput

from tripcrew.schemas import TripPlan
from tripcrew.tools.attractions import get_attractions
from tripcrew.tools.budget import estimate_budget
from tripcrew.tools.flights import search_flights
from tripcrew.tools.hotels import search_hotels
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


def build_consolidation_agent() -> Agent:
    """Merges intake and itinerary output into one TripPlan.

    Has exactly one tool, estimate_budget, and it's not optional: this agent
    used to have none, which meant it wrote Budget.total_usd itself as part
    of its own output_pydantic response, exactly the "LLM states a derived
    number" failure the rest of this project is built to avoid. Now it has
    to hand the gathered flight/hotel/attraction data to a real function and
    use what comes back.
    """
    llm = build_llm()
    return Agent(
        role="Trip Consolidator",
        goal=(
            "Merge the intake and itinerary research into one coherent trip "
            "plan. Call the Budget Estimator tool with the actual flight, "
            "hotel, and attraction data to get the budget, never write a "
            "total from memory."
        ),
        backstory=(
            "A meticulous editor who never lets a total stand unless it "
            "came back from the Budget Estimator tool, fed with the real "
            "flight, hotel, and attraction costs already gathered."
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
    """Depends on intake_task's output for destination and dates."""
    return Task(
        description=(
            "Using the destination and dates from the intake research, find "
            "attractions worth visiting and check the weather forecast. Use "
            "the forecast to note which days suit outdoor attractions and "
            "which don't. Both tools return an empty result rather than an "
            "error when they can't actually look something up -- treat an "
            "empty result as 'not available for this trip,' don't invent a "
            "plausible-sounding attraction or forecast to fill the gap."
        ),
        expected_output=(
            "A list of attractions with the weather context that informed "
            "how they'd be sequenced across the trip's days, or a plain note "
            "that attractions and/or weather weren't available if the tools "
            "came back empty."
        ),
        agent=agent,
        context=[intake_task],
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
            "plausible-sounding attraction or forecast to fill the gap."
        ),
        expected_output=(
            "A list of attractions with the weather context that informed "
            "how they'd be sequenced across the trip's days, or a plain note "
            "that attractions and/or weather weren't available if the tools "
            "came back empty."
        ),
        agent=agent,
    )


def build_consolidation_task(agent: Agent, intake_task: Task, itinerary_task: Task) -> Task:
    """Depends on both prior tasks. Only task with a pydantic output type --
    this is the point where a TripPlan actually exists as structured data.
    """
    return Task(
        description=(
            "Merge the intake and itinerary research into one TripPlan. "
            "Call the Budget Estimator tool with the actual flights, hotel, "
            "attractions, and number of nights from the earlier research, "
            "and use exactly what it returns as the budget. Don't compute "
            "or state a total yourself, and don't change the numbers the "
            "tool gives back, including unpriced_categories."
        ),
        expected_output=(
            "A complete TripPlan with a budget that came from the Budget "
            "Estimator tool, not a total you wrote yourself."
        ),
        agent=agent,
        context=[intake_task, itinerary_task],
        output_pydantic=TripPlan,
    )


def build_consolidation_task_from_plan(agent: Agent, intake_plan: TripPlan, itinerary_task: Task) -> Task:
    """Same job as build_consolidation_task, paired with
    build_itinerary_task_from_plan. Needs the intake plan's flights and
    hotel data verbatim to call the Budget Estimator tool correctly, so
    the whole plan gets embedded as JSON rather than just destination/days
    -- unlike the itinerary task, this one can't get away with a short
    summary. interpolate_only (CrewAI's template-filling step, runs on
    every task description during kickoff) only substitutes bare
    {identifier} placeholders, confirmed by reading its source, so the
    embedded JSON's own braces don't collide with it.
    """
    intake_json = intake_plan.model_dump_json(indent=2)
    return Task(
        description=(
            "The intake research already gathered this data, use it "
            f"exactly as given, don't re-derive or restate it differently:\n\n{intake_json}\n\n"
            "Merge this with the itinerary research into one TripPlan. "
            "Call the Budget Estimator tool with the actual flights, hotel, "
            "attractions, and number of nights from the data above and the "
            "itinerary research, and use exactly what it returns as the "
            "budget. Don't compute or state a total yourself, and don't "
            "change the numbers the tool gives back, including "
            "unpriced_categories."
        ),
        expected_output=(
            "A complete TripPlan with a budget that came from the Budget "
            "Estimator tool, not a total you wrote yourself."
        ),
        agent=agent,
        context=[itinerary_task],
        output_pydantic=TripPlan,
    )


def build_presentation_task(agent: Agent, consolidation_task: Task) -> Task:
    """Depends on the consolidated TripPlan. Last task in the chain."""
    return Task(
        description=(
            "Turn the consolidated TripPlan into a clear, practical "
            "write-up for the traveler. Present exactly what's in the "
            "plan, don't add details the plan doesn't contain. If "
            "budget.unpriced_categories isn't empty, say plainly that the "
            "total doesn't include those categories, don't present it as a "
            "complete number."
        ),
        expected_output=(
            "A readable trip plan write-up covering flights, hotel, "
            "attractions, weather, and budget."
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
    starts from itinerary research, with the known destination/days/
    flights/hotel baked into the remaining tasks' descriptions instead of
    coming from a freshly-run intake_task's context. That used to be a
    "known simplification" (rerunning intake from scratch, one redundant
    LLM call every message) -- redundant LLM calls are exactly what burns
    through Groq's free-tier rate limit fastest, so it stopped being a
    minor inefficiency and became a real reason a plan could fail outright.

    Passing no intake_plan keeps the original four-task chain, for tests
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
    consolidation_agent = build_consolidation_agent()
    presentation_agent = build_presentation_agent()

    if intake_plan is not None:
        itinerary_task = build_itinerary_task_from_plan(itinerary_agent, intake_plan)
        consolidation_task = build_consolidation_task_from_plan(consolidation_agent, intake_plan, itinerary_task)
        presentation_task = build_presentation_task(presentation_agent, consolidation_task)
        return Crew(
            agents=[itinerary_agent, consolidation_agent, presentation_agent],
            tasks=[itinerary_task, consolidation_task, presentation_task],
            process=Process.sequential,
            tracing=False,
            verbose=True,
            task_callback=task_callback,
        )

    intake_agent = build_intake_agent()
    intake_task = build_intake_task(intake_agent)
    itinerary_task = build_itinerary_task(itinerary_agent, intake_task)
    consolidation_task = build_consolidation_task(consolidation_agent, intake_task, itinerary_task)
    presentation_task = build_presentation_task(presentation_agent, consolidation_task)

    return Crew(
        agents=[intake_agent, itinerary_agent, consolidation_agent, presentation_agent],
        tasks=[intake_task, itinerary_task, consolidation_task, presentation_task],
        process=Process.sequential,
        tracing=False,
        verbose=True,
        task_callback=task_callback,
    )


def build_intake_crew() -> Crew:
    """A one-task crew running intake alone, for the clarification-gathering
    loop in app.py. Checking open_questions here is cheaper than running
    the full four-agent pipeline just to find out something's missing.

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
