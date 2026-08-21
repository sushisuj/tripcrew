"""Smoke tests for the PDF export module.

Not checking rendered layout (reportlab's own test suite already covers
that), just that a real TripPlan -- full, partially empty, or missing
optional pieces entirely -- produces valid PDF bytes without raising.
"""

from pypdf import PdfReader
from io import BytesIO

from tripcrew.pdf_export import build_trip_pdf
from tripcrew.schemas import Attraction, Budget, Flight, Hotel, TripPlan, WeatherReport


def _page_count(pdf_bytes: bytes) -> int:
    return len(PdfReader(BytesIO(pdf_bytes)).pages)


def test_full_trip_plan_produces_a_valid_pdf():
    plan = TripPlan(
        destination="Lisbon",
        days=4,
        flights=[
            Flight(
                origin="JFK",
                destination="LIS",
                departure_date="2026-08-24",
                airline="Air France",
                price_usd=544.67,
                source="mocked",
            ),
            Flight(
                origin="JFK",
                destination="LIS",
                departure_date="2026-08-24",
                airline="Lufthansa",
                price_usd=642.16,
                source="mocked",
            ),
        ],
        hotel=Hotel(
            name="Hotel Central",
            city="Lisbon",
            check_in="2026-08-24",
            check_out="2026-08-28",
            price_per_night_usd=203.90,
            source="mocked",
        ),
        attractions=[Attraction(name="Belem Tower", city="Lisbon", category="tourism.sights")],
        weather=[WeatherReport(city="Lisbon", date="2026-08-24", summary="light rain, 20C")],
        budget=Budget(flights_usd=544.67, hotel_usd=815.60, attractions_usd=0, unpriced_categories=["attractions"]).recompute(),
    )

    pdf_bytes = build_trip_pdf(plan, write_up="A four-day trip to Lisbon with mild rain on arrival.")

    assert pdf_bytes.startswith(b"%PDF")
    assert _page_count(pdf_bytes) >= 1


def test_minimal_trip_plan_with_no_flights_hotel_or_attractions_still_renders():
    # Empty lists/None are all real states this can be called with -- an
    # early clarification-loop draft, or a trip where a tool came back
    # empty. Should degrade to "not available" text, not crash.
    plan = TripPlan(destination="Nowhere", days=1)

    pdf_bytes = build_trip_pdf(plan, write_up="")

    assert pdf_bytes.startswith(b"%PDF")
    assert _page_count(pdf_bytes) >= 1


def test_flight_missing_a_price_does_not_crash_the_cheapest_lookup():
    # min() over an empty "priced flights" generator would raise without
    # the explicit default=None in build_trip_pdf -- covering the case
    # where every flight is unpriced.
    plan = TripPlan(
        destination="Lisbon",
        days=2,
        flights=[Flight(origin="JFK", destination="LIS", departure_date="2026-08-24", source="mocked")],
    )

    pdf_bytes = build_trip_pdf(plan, write_up="")

    assert pdf_bytes.startswith(b"%PDF")


def test_special_characters_in_agent_text_do_not_break_rendering():
    # write_up comes from an LLM, attraction names from a live API --
    # reportlab's Paragraph parser treats <, >, & as XML, so unescaped
    # input in a Paragraph would raise inside doc.build(), not just render
    # oddly. Table cells are the opposite case: they render text literally
    # rather than parsing it as markup, so escaping *there* would leave
    # visible "&amp;"/"&gt;" artifacts on the page instead of the real
    # characters -- caught by rendering an actual sample and reading it
    # back with pypdf, not just checking the build doesn't raise.
    plan = TripPlan(
        destination="Lisbon",
        days=1,
        flights=[
            Flight(
                origin="New York",
                destination="Lisbon",
                departure_date="2026-08-24",
                price_usd=500,
                source="mocked",
            )
        ],
        attractions=[Attraction(name="Fish & Chips <Landmark>", city="Lisbon")],
    )

    pdf_bytes = build_trip_pdf(plan, write_up="Budget < $2000 && flights > expected")

    assert pdf_bytes.startswith(b"%PDF")
    text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "Fish & Chips <Landmark>" in text
    assert "New York -> Lisbon" in text
    assert "&amp;" not in text and "&gt;" not in text and "&lt;" not in text
