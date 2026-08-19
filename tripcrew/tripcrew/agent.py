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

import crewai.llms.cache as _crewai_cache
from crewai import LLM, Agent, Crew, Process, Task

from tripcrew.schemas import TripPlan
from tripcrew.tools.attractions import get_attractions
from tripcrew.tools.budget import estimate_budget
from tripcrew.tools.flights import search_flights
from tripcrew.tools.hotels import search_hotels
from tripcrew.tools.weather import get_weather

# CrewAI (as of 1.15.x) unconditionally tags every message with a
# cache_breakpoint flag meant only for Anthropic's prompt-caching API, then
# sends that same flag to whatever provider is actually configured. Groq's
# API validates message schemas strictly and 400s on the unrecognized
# field: "property 'cache_breakpoint' is unsupported". Known upstream bug,
# github.com/crewAIInc/crewAI/issues/5886, fix PRs open but not merged as
# of this writing. This is the workaround from that issue: replace the
# tagging function with a no-op. Safe as long as the LLM stays on Groq (or
# any non-Anthropic provider); if this project ever switches back to an
# Anthropic model, remove this patch first or prompt caching silently
# stops working for it too.
_crewai_cache.mark_cache_breakpoint = lambda msg: msg


def build_llm() -> LLM:
    """Switched from NVIDIA NIM to Groq. LiteLLM has native Groq support, no
    base_url/api_key wrangling needed, just the `groq/` provider prefix and
    a GROQ_API_KEY in the environment (see .env.example).

    Model is Groq's own recommended replacement for llama-3.1-8b-instant,
    which was deprecated 08/16/26 -- the obvious small/fast Llama model
    isn't actually the one to reach for anymore. Confirmed against Groq's
    current model list before wiring it in, not assumed from memory.
    """
    return LLM(model="groq/openai/gpt-oss-20b")


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


def build_crew() -> Crew:
    """Assembles all four agents and their chained tasks into a
    Process.sequential Crew. This is what app.py should call, not the
    individual builder functions above -- those exist mainly so this
    function and tests can construct pieces independently.
    """
    intake_agent = build_intake_agent()
    itinerary_agent = build_itinerary_agent()
    consolidation_agent = build_consolidation_agent()
    presentation_agent = build_presentation_agent()

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
    )


def build_intake_crew() -> Crew:
    """A one-task crew running intake alone, for the clarification-gathering
    loop in app.py. Checking open_questions here is cheaper than running
    the full four-agent pipeline just to find out something's missing.

    Known simplification: once app.py decides to move on, it calls
    build_crew() next, which runs its own fresh intake task from scratch
    rather than reusing this one's already-satisfied result. That's one
    redundant LLM call, not a correctness problem, just not optimally
    efficient. Worth fixing later if it matters, not blocking for now.
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
