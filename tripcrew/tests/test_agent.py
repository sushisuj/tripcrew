"""Tests for the crew-assembly layer in agent.py.

Mostly about assemble_trip_plan(): the fix for a real bug where the
consolidation task's LLM re-authored attractions/weather/restaurants from
context instead of copying them, which is how a real London run ended up
with a corrupted weather summary ("Light rain, ~22C (approximate)
(approximate)"). itinerary_task and food_task now carry their own
output_pydantic (ItineraryResearch, FoodResearch, see schemas.py), and
assemble_trip_plan() is what actually substitutes their real output back
into the consolidated TripPlan -- these tests check that substitution
directly, with lightweight stand-ins for CrewOutput/TaskOutput rather than
a live crew run.

build_crew()'s task wiring (five tasks with no intake_plan, four with one,
and which output_pydantic each research task carries) is also covered here,
since nothing else in the suite exercises agent.py at all.

Also covers the day-clamping half of assemble_trip_plan(): Attraction.day/
Restaurant.day are genuine LLM-authored values (the itinerary/food agent's
own reasoning, not a tool's raw output, see Attraction.day's docstring in
schemas.py), so they're not restated the way attractions/weather/restaurants
themselves are, but they can still be wrong the way any model output can,
so anything outside 1..TripPlan.days gets reset to None rather than shown
as, say, "Day 7" on a 3-day trip.

And the research_gaps half: once attractions/restaurants/weather are the
real substituted values, assemble_trip_plan() evaluates them for empty or
thin results and reports each one in TripPlan.research_gaps, the "evaluate"
step that was missing when a real London run had attractions come back
empty and nothing downstream reacted to it (see _evaluate_research_gaps()'s
own docstring in agent.py).

And the genuinely-dynamic-sequencing half: itinerary and food research run
concurrently now (async_execution=True, see build_itinerary_task()'s own
docstring), since neither reads the other's output. That has one real
consequence covered here: task_callback can fire in either order depending
on which finishes first, so stage_label_for() identifies which stage just
finished from the output's own type instead of trusting call position --
tested directly against every output type build_crew(intake_plan=...)'s
four tasks can actually produce.

And the reasoning-trail half: extract_reasoning() pulls a task's own
free-text reasoning out of its real message transcript (TaskOutput.messages,
not .raw -- see that function's own docstring for why .raw doesn't work for
a task with output_pydantic set), and reasoning_entry_for() pairs that with
stage_label_for() so app.py's task_callback records a label and its
reasoning as one unit. Tested against fake message transcripts shaped like
crewai's real ones (assistant text, tool calls with no text, tool results),
not a live LLM call.
"""

from dataclasses import dataclass, field
from typing import Any

from tripcrew.agent import (
    PLANNING_STAGE_LABELS,
    assemble_trip_plan,
    build_crew,
    build_food_agent,
    build_food_task,
    build_food_task_from_plan,
    build_intake_agent,
    build_intake_task,
    build_itinerary_agent,
    build_itinerary_task,
    build_itinerary_task_from_plan,
    extract_reasoning,
    reasoning_entry_for,
    stage_label_for,
)
from tripcrew.schemas import (
    Attraction,
    Budget,
    FoodResearch,
    ItineraryResearch,
    Restaurant,
    TripPlan,
    WeatherReport,
)


@dataclass
class _FakeTaskOutput:
    """Stand-in for crewai.tasks.task_output.TaskOutput -- assemble_trip_plan()
    only ever reads .pydantic off each entry in result.tasks_output, so a
    real TaskOutput (which needs a live Task/Agent to construct) isn't
    needed here. messages defaults to empty since most tests here only
    care about .pydantic -- extract_reasoning()/reasoning_entry_for()'s own
    tests are the ones that actually populate it, as plain dicts shaped
    like crewai's real LLMMessage (a TypedDict, so a plain dict satisfies
    it structurally without needing the real type imported here).
    """

    pydantic: Any
    messages: list[dict] = field(default_factory=list)


@dataclass
class _FakeCrewOutput:
    """Stand-in for crewai.crews.crew_output.CrewOutput, same reasoning as
    _FakeTaskOutput: only .tasks_output is ever read.
    """

    tasks_output: list


def _corrupted_consolidation_plan() -> TripPlan:
    """A TripPlan shaped like the consolidation task's own (wrong) output:
    it has real flights/hotel/budget, but its attractions/weather/
    restaurants are the LLM's own re-authored (and here, corrupted) retelling
    rather than the tools' actual output. This is the exact shape
    assemble_trip_plan() has to fix.
    """
    return TripPlan(
        destination="London",
        days=3,
        attractions=[Attraction(name="Wrong Museum", city="London")],
        weather=[
            WeatherReport(
                city="London",
                date="2026-09-01",
                summary="Light rain, ~22■C (approximate) (approximate)",
                is_approximate=True,
            )
        ],
        restaurants=[Restaurant(name="Wrong Cafe", city="London")],
        budget=Budget(flights_usd=500, hotel_usd=300, total_usd=800),
    )


def test_assemble_trip_plan_overwrites_research_fields_with_real_tool_output():
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[Attraction(name="Tower of London", city="London")],
        weather=[WeatherReport(city="London", date="2026-09-01", summary="Light rain, 22C")],
    )
    real_food = FoodResearch(restaurants=[Restaurant(name="Dishoom", city="London")])

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
            _FakeTaskOutput(pydantic=None),  # presentation task: no output_pydantic
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan is not None
    # The consolidation task's own budget/destination survive untouched --
    # only the research fields get replaced.
    assert plan.destination == "London"
    assert plan.budget.total_usd == 800
    assert [a.name for a in plan.attractions] == ["Tower of London"]
    assert [w.summary for w in plan.weather] == ["Light rain, 22C"]
    assert [r.name for r in plan.restaurants] == ["Dishoom"]


def test_assemble_trip_plan_leaves_research_fields_alone_if_not_found():
    # Defensive path: if a research task's structured output isn't in
    # tasks_output for some reason, don't wipe out what the consolidation
    # task already had -- only overwrite when a real replacement exists.
    consolidation_output = _corrupted_consolidation_plan()
    result = _FakeCrewOutput(tasks_output=[_FakeTaskOutput(pydantic=consolidation_output)])

    plan = assemble_trip_plan(result)

    assert plan is not None
    assert [a.name for a in plan.attractions] == ["Wrong Museum"]
    assert [r.name for r in plan.restaurants] == ["Wrong Cafe"]


def test_assemble_trip_plan_returns_none_without_a_trip_plan():
    result = _FakeCrewOutput(tasks_output=[_FakeTaskOutput(pydantic=None)])
    assert assemble_trip_plan(result) is None


def test_assemble_trip_plan_clears_an_out_of_range_day():
    # A 3-day trip: day=7 on an attraction and day=0 on a restaurant are
    # both impossible values the itinerary/food agent shouldn't have
    # produced, but could -- clamp rather than show a broken day number.
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[
            Attraction(name="Tower of London", city="London", day=2),
            Attraction(name="Impossible Museum", city="London", day=7),
        ],
        weather=[],
    )
    real_food = FoodResearch(
        restaurants=[
            Restaurant(name="Dishoom", city="London", day=1),
            Restaurant(name="Zero Day Cafe", city="London", day=0),
        ]
    )

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan is not None
    assert plan.days == 3
    days_by_attraction = {a.name: a.day for a in plan.attractions}
    assert days_by_attraction["Tower of London"] == 2
    assert days_by_attraction["Impossible Museum"] is None
    days_by_restaurant = {r.name: r.day for r in plan.restaurants}
    assert days_by_restaurant["Dishoom"] == 1
    assert days_by_restaurant["Zero Day Cafe"] is None


def test_assemble_trip_plan_leaves_a_valid_day_alone():
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[Attraction(name="Tower of London", city="London", day=3)],
        weather=[],
    )
    real_food = FoodResearch(restaurants=[Restaurant(name="Dishoom", city="London", day=None)])

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan is not None
    assert plan.attractions[0].day == 3
    assert plan.restaurants[0].day is None


def test_assemble_trip_plan_strips_a_doubled_approximate_marker_from_weather():
    # Regression test for the actual real-PDF bug: the itinerary task's own
    # structured output (not just the consolidation task's retelling this
    # file's other tests already cover) can independently add
    # "(approximate)" to a summary despite being told to copy get_weather()'s
    # text verbatim. That plus pdf_export.py's own append is how a real PDF
    # ended up with "Light rain, ~22C (approximate) (approximate)".
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[],
        weather=[
            WeatherReport(
                city="London",
                date="2026-09-01",
                summary="Light rain, ~22C (approximate) (approximate)",
                is_approximate=True,
            )
        ],
    )

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan.weather[0].summary == "Light rain, ~22C"
    assert plan.weather[0].is_approximate is True


def test_assemble_trip_plan_strips_a_single_approximate_marker_from_weather():
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[],
        weather=[
            WeatherReport(
                city="Lisbon",
                date="2026-10-01",
                summary="clear sky, 21.69C (approximate)",
                is_approximate=True,
            )
        ],
    )

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan.weather[0].summary == "clear sky, 21.69C"


def test_assemble_trip_plan_leaves_a_clean_weather_summary_alone():
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[],
        weather=[WeatherReport(city="Lisbon", date="2026-10-01", summary="clear sky, 21.69C", is_approximate=True)],
    )

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan.weather[0].summary == "clear sky, 21.69C"


def test_assemble_trip_plan_flags_empty_attractions_and_restaurants_as_research_gaps():
    # The real bug this closes: a London run had get_attractions() come back
    # empty and nothing downstream reacted to it, the write-up just quietly
    # described a trip with no attractions in it. research_gaps is what
    # makes that visible instead of silent.
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[],
        weather=[WeatherReport(city="London", date="2026-09-01", summary="Light rain, 22C")],
    )
    real_food = FoodResearch(restaurants=[])

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan is not None
    assert any("Attractions" in gap and "no results found" in gap for gap in plan.research_gaps)
    assert any("Restaurants" in gap and "no results found" in gap for gap in plan.research_gaps)
    assert not any(gap.startswith("Weather") for gap in plan.research_gaps)


def test_assemble_trip_plan_flags_a_single_result_as_thin_not_just_zero():
    # One attraction and one restaurant for a whole trip isn't meaningfully
    # different from zero for planning purposes -- THIN_RESEARCH_THRESHOLD
    # exists so this gets flagged the same as an outright empty list.
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[Attraction(name="Tower of London", city="London")],
        weather=[WeatherReport(city="London", date="2026-09-01", summary="Light rain, 22C")],
    )
    real_food = FoodResearch(restaurants=[Restaurant(name="Dishoom", city="London")])

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert any("Attractions" in gap and "only 1 result found" in gap for gap in plan.research_gaps)
    assert any("Restaurants" in gap and "only 1 result found" in gap for gap in plan.research_gaps)


def test_assemble_trip_plan_reports_no_gaps_once_theres_enough_of_everything():
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[
            Attraction(name="Tower of London", city="London"),
            Attraction(name="British Museum", city="London"),
        ],
        weather=[WeatherReport(city="London", date="2026-09-01", summary="Light rain, 22C")],
    )
    real_food = FoodResearch(
        restaurants=[
            Restaurant(name="Dishoom", city="London"),
            Restaurant(name="Borough Market", city="London"),
        ]
    )

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan.research_gaps == []


def test_assemble_trip_plan_flags_missing_weather_as_a_research_gap_too():
    consolidation_output = _corrupted_consolidation_plan()
    real_itinerary = ItineraryResearch(
        attractions=[
            Attraction(name="Tower of London", city="London"),
            Attraction(name="British Museum", city="London"),
        ],
        weather=[],
    )
    real_food = FoodResearch(
        restaurants=[
            Restaurant(name="Dishoom", city="London"),
            Restaurant(name="Borough Market", city="London"),
        ]
    )

    result = _FakeCrewOutput(
        tasks_output=[
            _FakeTaskOutput(pydantic=real_itinerary),
            _FakeTaskOutput(pydantic=real_food),
            _FakeTaskOutput(pydantic=consolidation_output),
        ]
    )

    plan = assemble_trip_plan(result)

    assert plan.research_gaps == ["Weather: no forecast could be found for London."]


def test_itinerary_tasks_use_itinerary_research_as_output_type():
    plan = TripPlan(destination="Paris", days=3)
    intake_task = build_intake_task(build_intake_agent())
    assert build_itinerary_task(build_itinerary_agent(), intake_task).output_pydantic is ItineraryResearch
    assert build_itinerary_task_from_plan(build_itinerary_agent(), plan).output_pydantic is ItineraryResearch


def test_food_tasks_use_food_research_as_output_type():
    plan = TripPlan(destination="Paris", days=3)
    intake_task = build_intake_task(build_intake_agent())
    assert build_food_task(build_food_agent(), intake_task).output_pydantic is FoodResearch
    assert build_food_task_from_plan(build_food_agent(), plan).output_pydantic is FoodResearch


def test_build_crew_wires_five_tasks_without_an_intake_plan():
    crew = build_crew()
    assert len(crew.tasks) == 5
    assert len(crew.agents) == 5


def test_build_crew_wires_four_tasks_with_an_intake_plan():
    plan = TripPlan(destination="Paris", days=3)
    crew = build_crew(intake_plan=plan)
    assert len(crew.tasks) == 4
    assert len(crew.agents) == 4
    # Order matters: itinerary and food research have to finish before
    # consolidation reads their output, and presentation reads
    # consolidation's -- Process.sequential relies on list order alone.
    roles = [t.agent.role for t in crew.tasks]
    assert roles == [
        "Itinerary Researcher",
        "Food Researcher",
        "Trip Consolidator",
        "Trip Presenter",
    ]


def test_itinerary_and_food_tasks_run_concurrently_in_the_five_task_crew():
    # async_execution=True is the actual dynamic-sequencing decision: CrewAI
    # runs these two concurrently since neither reads the other's output
    # (both only depend on intake_task, see build_itinerary_task()'s own
    # docstring), instead of Process.sequential forcing one to wait on the
    # other for no real reason. Every other task stays synchronous --
    # intake has to finish before either research task can start, and
    # consolidation/presentation both genuinely need real upstream output.
    crew = build_crew()
    async_by_role = {t.agent.role: bool(t.async_execution) for t in crew.tasks}
    assert async_by_role == {
        "Trip Intake Coordinator": False,
        "Itinerary Researcher": True,
        "Food Researcher": True,
        "Trip Consolidator": False,
        "Trip Presenter": False,
    }


def test_itinerary_and_food_tasks_from_plan_also_run_concurrently():
    plan = TripPlan(destination="Paris", days=3)
    crew = build_crew(intake_plan=plan)
    async_by_role = {t.agent.role: bool(t.async_execution) for t in crew.tasks}
    assert async_by_role == {
        "Itinerary Researcher": True,
        "Food Researcher": True,
        "Trip Consolidator": False,
        "Trip Presenter": False,
    }


def test_stage_label_for_routes_by_output_type_not_call_order():
    # The actual reason this function exists: with itinerary and food
    # research running concurrently, whichever finishes first calls
    # task_callback first -- this has to identify the stage from the
    # output itself, not from how many times it's been called so far.
    assert stage_label_for(_FakeTaskOutput(pydantic=ItineraryResearch())) == "Researching attractions & weather"
    assert stage_label_for(_FakeTaskOutput(pydantic=FoodResearch())) == "Researching restaurants & cafes"
    consolidated = TripPlan(destination="Paris", days=3)
    assert stage_label_for(_FakeTaskOutput(pydantic=consolidated)) == "Consolidating the plan & budget"


def test_stage_label_for_the_presentation_task_has_no_output_pydantic():
    assert stage_label_for(_FakeTaskOutput(pydantic=None)) == "Writing it up"


def test_stage_label_for_returns_none_for_an_unexpected_output_type():
    # Defensive: not expected in normal operation, but a label lookup
    # failing should never be the reason the task_callback itself raises.
    assert stage_label_for(_FakeTaskOutput(pydantic="not a real task output")) is None


def test_planning_stage_labels_lists_all_four_stages_in_reading_order():
    # app.py renders completed stages against this fixed order rather than
    # the order they actually finished in, so the checklist stays visually
    # consistent between runs even though itinerary/food research's real
    # completion order can vary.
    assert PLANNING_STAGE_LABELS == [
        "Researching attractions & weather",
        "Researching restaurants & cafes",
        "Consolidating the plan & budget",
        "Writing it up",
    ]


def test_extract_reasoning_keeps_only_the_assistant_s_own_text():
    # A real task transcript mixes assistant text, tool calls (assistant
    # role, no text -- crewai's sanitizer keeps tool_calls but content is
    # often empty for these), and tool result messages (role "tool"). Only
    # the first kind is the agent's own reasoning.
    task_output = _FakeTaskOutput(
        pydantic=None,
        messages=[
            {"role": "system", "content": "You are a researcher..."},
            {"role": "user", "content": "Find attractions in Lisbon."},
            {"role": "assistant", "content": "I'll check attractions, then the forecast."},
            {"role": "assistant", "content": "", "tool_calls": [{"name": "get_attractions"}]},
            {"role": "tool", "content": '[{"name": "Belem Tower"}]', "name": "get_attractions"},
            {"role": "assistant", "content": "Got one attraction, now checking weather."},
        ],
    )

    assert extract_reasoning(task_output) == [
        "I'll check attractions, then the forecast.",
        "Got one attraction, now checking weather.",
    ]


def test_extract_reasoning_returns_an_empty_list_when_theres_nothing_to_show():
    # A task that only ever called tools with no surrounding text (or a
    # transcript that wasn't captured at all) shouldn't raise, just
    # report no reasoning -- an empty trail is honest, not a bug to fix.
    assert extract_reasoning(_FakeTaskOutput(pydantic=None, messages=[])) == []
    only_tool_calls = _FakeTaskOutput(
        pydantic=None,
        messages=[{"role": "assistant", "content": "", "tool_calls": [{"name": "get_weather"}]}],
    )
    assert extract_reasoning(only_tool_calls) == []


def test_reasoning_entry_for_pairs_the_stage_label_with_its_own_reasoning():
    task_output = _FakeTaskOutput(
        pydantic=ItineraryResearch(),
        messages=[{"role": "assistant", "content": "Checking Lisbon's attractions first."}],
    )

    entry = reasoning_entry_for(task_output)

    assert entry == ("Researching attractions & weather", ["Checking Lisbon's attractions first."])


def test_reasoning_entry_for_returns_none_for_an_unexpected_output_type():
    # Same defensive case as stage_label_for()'s own test -- a label lookup
    # failing here should never be the reason task_callback raises.
    assert reasoning_entry_for(_FakeTaskOutput(pydantic="not a real task output")) is None
