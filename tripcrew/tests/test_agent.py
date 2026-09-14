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
"""

from dataclasses import dataclass
from typing import Any

from tripcrew.agent import (
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
    needed here.
    """

    pydantic: Any


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
