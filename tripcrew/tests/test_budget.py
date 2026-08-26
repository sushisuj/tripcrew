"""Tests for estimate_budget(), the one function this project's whole
groundedness principle rests on: don't let an LLM state a derived number,
compute it from the parts in code. Everything here is pure arithmetic on
pydantic models, no network, no LLM, so there's no excuse for this being
the last untested piece of tripcrew/tools/ -- it's also the one where a
silent regression (x or 0 creeping back in, say) would be the hardest to
notice just by looking at a rendered plan.
"""

from tripcrew.schemas import Attraction, Flight, Hotel
from tripcrew.tools.budget import estimate_budget


def _flight(price_usd=None, origin="JFK", destination="LIS"):
    return Flight(origin=origin, destination=destination, departure_date="2026-08-24", price_usd=price_usd, source="mocked")


def _hotel(price_per_night_usd=None):
    return Hotel(name="Hotel Central", city="Lisbon", check_in="2026-08-24", check_out="2026-08-28", price_per_night_usd=price_per_night_usd, source="mocked")


def _attraction(estimated_cost_usd=None, name="Belem Tower"):
    return Attraction(name=name, city="Lisbon", estimated_cost_usd=estimated_cost_usd)


def test_picks_the_cheapest_priced_flight_not_the_first_one():
    # Regression test for the actual bug: flights[:1] used to be the real
    # logic despite a comment claiming "cheapest," so a pricier flight could
    # get reported while a cheaper one sat right next to it in the list.
    flights = [_flight(price_usd=899.00), _flight(price_usd=544.67), _flight(price_usd=612.30)]
    budget = estimate_budget.func(flights=flights, hotel=None, attractions=[], nights=4)
    assert budget.flights_usd == 544.67


def test_unpriced_flights_are_ignored_when_a_priced_one_exists():
    flights = [_flight(price_usd=None), _flight(price_usd=544.67)]
    budget = estimate_budget.func(flights=flights, hotel=None, attractions=[], nights=4)
    assert budget.flights_usd == 544.67
    assert "flights" not in budget.unpriced_categories


def test_all_flights_unpriced_flags_the_category_instead_of_defaulting_to_zero_silently():
    flights = [_flight(price_usd=None), _flight(price_usd=None)]
    budget = estimate_budget.func(flights=flights, hotel=None, attractions=[], nights=4)
    assert budget.flights_usd == 0
    assert "flights" in budget.unpriced_categories


def test_no_flights_at_all_is_not_the_same_as_unpriced_flights():
    # An empty list means "nothing to report," not "we don't know the
    # price" -- only flag the category when flights exist but none of them
    # came back with a price.
    budget = estimate_budget.func(flights=[], hotel=None, attractions=[], nights=4)
    assert budget.flights_usd == 0
    assert "flights" not in budget.unpriced_categories


def test_hotel_total_is_price_per_night_times_nights():
    budget = estimate_budget.func(flights=[], hotel=_hotel(price_per_night_usd=203.90), attractions=[], nights=4)
    assert budget.hotel_usd == 203.90 * 4


def test_hotel_present_with_no_price_is_flagged_unpriced():
    budget = estimate_budget.func(flights=[], hotel=_hotel(price_per_night_usd=None), attractions=[], nights=4)
    assert budget.hotel_usd == 0
    assert "hotel" in budget.unpriced_categories


def test_no_hotel_at_all_is_not_flagged_unpriced():
    budget = estimate_budget.func(flights=[], hotel=None, attractions=[], nights=4)
    assert budget.hotel_usd == 0
    assert "hotel" not in budget.unpriced_categories


def test_attractions_with_no_cost_data_are_flagged_unpriced_not_treated_as_free():
    # The real-world case: Geoapify never returns cost data, so this is
    # what every actual run hits. attractions_usd used to be a silent 0
    # with nothing telling the presentation task the total excludes it.
    attractions = [_attraction(estimated_cost_usd=None), _attraction(estimated_cost_usd=None, name="Oceanario")]
    budget = estimate_budget.func(flights=[], hotel=None, attractions=attractions, nights=4)
    assert budget.attractions_usd == 0
    assert "attractions" in budget.unpriced_categories


def test_attractions_sums_only_the_priced_ones():
    attractions = [_attraction(estimated_cost_usd=15.0), _attraction(estimated_cost_usd=25.5, name="Oceanario")]
    budget = estimate_budget.func(flights=[], hotel=None, attractions=attractions, nights=4)
    assert budget.attractions_usd == 40.5


def test_partially_priced_attractions_are_not_flagged_unpriced():
    # Documents the actual behavior, not necessarily the ideal one: the
    # category is only flagged when *none* of the attractions have a price,
    # so a mix of priced and unpriced attractions reports a real (if
    # incomplete) total without a flag. Worth knowing if this ever needs
    # tightening -- see CLAUDE.md before changing this on a hunch.
    attractions = [_attraction(estimated_cost_usd=15.0), _attraction(estimated_cost_usd=None, name="Oceanario")]
    budget = estimate_budget.func(flights=[], hotel=None, attractions=attractions, nights=4)
    assert budget.attractions_usd == 15.0
    assert "attractions" not in budget.unpriced_categories


def test_total_is_computed_from_the_parts_not_stated_separately():
    flights = [_flight(price_usd=544.67)]
    budget = estimate_budget.func(flights=flights, hotel=_hotel(price_per_night_usd=100.0), attractions=[_attraction(estimated_cost_usd=20.0)], nights=4)
    assert budget.total_usd == 544.67 + 400.0 + 20.0


def test_accepts_plain_dicts_the_way_crewai_actually_hands_them_over():
    # CrewAI deserializes the LLM's tool call JSON into plain dicts, not
    # Flight/Hotel/Attraction instances, despite the args_schema describing
    # the nested shape -- confirmed by calling this directly and hitting
    # AttributeError on a dict before the model_validate() coercion was
    # added. This is what actually exercises the crew end to end, not the
    # typed-object calls above.
    flights = [{"origin": "JFK", "destination": "LIS", "departure_date": "2026-08-24", "price_usd": 544.67, "source": "mocked"}]
    hotel = {"name": "Hotel Central", "city": "Lisbon", "check_in": "2026-08-24", "check_out": "2026-08-28", "price_per_night_usd": 100.0, "source": "mocked"}
    attractions = [{"name": "Belem Tower", "city": "Lisbon", "estimated_cost_usd": 20.0}]
    budget = estimate_budget.func(flights=flights, hotel=hotel, attractions=attractions, nights=4)
    assert budget.total_usd == 544.67 + 400.0 + 20.0
