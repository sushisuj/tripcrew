"""Live-judge evals for the presentation task's write-up: does it actually
say what's in the real TripPlan, or does it drift the way the consolidation
task's own restating once did (the corrupted weather summary bug -- see
agent.py's assemble_trip_plan() docstring)? A plain pytest assertion can
check that a field equals an expected value; it can't check "does this
sentence accurately reflect that data," which is exactly what an LLM-judge
metric is for, and exactly the gap promptfoo/deepeval exist to close in
this project's own evaluate-and-react story (see CLAUDE.md).

Marked `eval` (see pytest.ini's `markers` and `addopts = -m "not eval"`),
so a plain `pytest` run skips this file entirely -- every test here calls a
real judge model (TripCrewJudgeLLM, agent.py's own build_llm() under
deepeval's interface) over the network, the same live-service line the rest
of this project's test suite deliberately stays on the mocked side of. Run
these with `pytest -m eval`; needs the same .env this project already asks
for (OPENAI_API_KEY/OPENAI_API_BASE), nothing extra -- see judge_llm.py's
own docstring for why no second API key is needed.

Two cases, not an exhaustive suite: one write-up that's faithful to its
plan, one that fabricates an attraction the plan never produced. Building
out a full suite (more fabrication shapes, a case for a dropped
research_gap, a case for a misstated price) is real future work, not
something to fake here just to pad test count.
"""

import pytest
from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric, HallucinationMetric
from deepeval.test_case import LLMTestCase

from tripcrew.evals.context import trip_plan_context
from tripcrew.evals.judge_llm import TripCrewJudgeLLM
from tripcrew.schemas import Attraction, Budget, Flight, Hotel, Restaurant, TripPlan, WeatherReport

pytestmark = pytest.mark.eval


def _lisbon_plan() -> TripPlan:
    return TripPlan(
        destination="Lisbon",
        days=3,
        flights=[
            Flight(
                origin="JFK",
                destination="LIS",
                departure_date="2026-09-01",
                airline="Air France",
                price_usd=544.67,
                source="mocked",
            )
        ],
        hotel=Hotel(
            name="Hotel Central",
            city="Lisbon",
            check_in="2026-09-01",
            check_out="2026-09-04",
            price_per_night_usd=203.90,
            source="mocked",
        ),
        attractions=[Attraction(name="Belem Tower", city="Lisbon", category="tourism.sights", day=1)],
        restaurants=[Restaurant(name="Cervejaria Ramiro", city="Lisbon", category="catering.restaurant", day=1)],
        weather=[WeatherReport(city="Lisbon", date="2026-09-01", summary="Light rain, 20C")],
        budget=Budget(
            flights_usd=544.67,
            hotel_usd=611.70,
            attractions_usd=0,
            restaurants_usd=0,
            unpriced_categories=["attractions", "restaurants"],
        ).recompute(),
    )


def test_a_faithful_writeup_passes_faithfulness_and_hallucination():
    plan = _lisbon_plan()
    write_up = (
        "Your 3-day Lisbon trip: fly Air France from JFK on 2026-09-01 for $544.67, "
        "stay at Hotel Central from 2026-09-01 to 2026-09-04 at $203.90 a night. "
        "Day 1: visit Belem Tower, and Cervejaria Ramiro is a nearby restaurant option "
        "(not a rated recommendation). Weather on 2026-09-01 is light rain, 20C. "
        "Budget: $544.67 for flights plus $611.70 for the hotel, $1,156.37 total -- "
        "attractions and restaurants aren't included, no price data was available "
        "for those categories."
    )
    plan_context = trip_plan_context(plan)
    # FaithfulnessMetric and HallucinationMetric each want the same real
    # data under a different LLMTestCase field -- confirmed directly against
    # deepeval's source (each metric's own _required_params):
    # FaithfulnessMetric needs retrieval_context, HallucinationMetric needs
    # context. Not a typo to only set one of the two.
    test_case = LLMTestCase(
        input="Plan a 3-day trip to Lisbon.",
        actual_output=write_up,
        retrieval_context=plan_context,
        context=plan_context,
    )
    judge = TripCrewJudgeLLM()
    assert_test(
        test_case,
        [
            FaithfulnessMetric(model=judge, threshold=0.7),
            # threshold is the MINIMUM passing score as of deepeval's
            # current HallucinationMetric (1 = fully grounded, 0 = fully
            # hallucinated, same direction as every other deepeval metric
            # now) -- confirmed by the metric's own deprecation notice, not
            # the older "threshold = maximum allowed violation rate"
            # convention a lower number like 0.3 would have meant before.
            HallucinationMetric(model=judge, threshold=0.7),
        ],
    )


def test_a_writeup_that_invents_an_attraction_fails_faithfulness():
    # The actual regression this guards against: a write-up stating
    # something the real TripPlan never produced, the same class of drift
    # that once let the consolidation task's LLM introduce a corrupted
    # weather summary the research tools never produced (see
    # assemble_trip_plan()'s docstring). A hardcoded, unambiguous
    # fabrication (the Louvre is in Paris, not Lisbon, and isn't in this
    # plan's attractions at all) is a clean case a faithfulness judge
    # should reliably catch, not a borderline one.
    plan = _lisbon_plan()
    write_up = (
        "Your 3-day Lisbon trip includes a visit to the Louvre, one of the "
        "world's most famous museums, along with Belem Tower."
    )
    test_case = LLMTestCase(
        input="Plan a 3-day trip to Lisbon.",
        actual_output=write_up,
        retrieval_context=trip_plan_context(plan),
    )
    judge = TripCrewJudgeLLM()
    metric = FaithfulnessMetric(model=judge, threshold=0.7)

    metric.measure(test_case)

    assert metric.score < metric.threshold, (
        f"Expected the Louvre fabrication to fail faithfulness, scored {metric.score}. "
        f"Judge reasoning: {metric.reason}"
    )
