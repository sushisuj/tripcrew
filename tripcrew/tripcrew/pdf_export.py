"""Renders a finished TripPlan to a downloadable PDF.

Not a CrewAI @tool -- nothing here is called by an agent, this is a plain
utility app.py calls directly once a trip is fully planned. That's also why
it lives at the package root next to app.py/agent.py/schemas.py instead of
under tripcrew/tools/, which CLAUDE.md documents as agent-facing tools
specifically.

Every number on the page comes straight from TripPlan.budget, computed by
the real Budget Estimator tool (see tools/budget.py) -- this module never
re-derives a total, sum, or price of its own. That's the same groundedness
rule the rest of this project is built around, just applied to a PDF
instead of a chat response: if it's a number, it came from a tool, not
from formatting code.
"""

import unicodedata
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from tripcrew.schemas import TripPlan

_STYLES = getSampleStyleSheet()
_HEADING_STYLE = ParagraphStyle("SectionHeading", parent=_STYLES["Heading2"], spaceBefore=14, spaceAfter=6)
_SUBHEADING_STYLE = ParagraphStyle("DayHeading", parent=_STYLES["Heading3"], spaceBefore=8, spaceAfter=4)
_TABLE_HEADER_BG = colors.HexColor("#6E8CC7")

# reportlab's base Helvetica font uses WinAnsiEncoding (essentially CP1252),
# not full Unicode, so a character outside that set has no glyph to draw and
# renders as a missing-glyph box instead of failing loudly. Confirmed as a
# real defect, not hypothetical: a real London PDF rendered "Check-in" as
# "Check[box]in" in the write-up text -- pypdf's own extraction of that PDF
# shows U+25A0 at each occurrence, the placeholder pypdf itself reports for
# any glyph with no usable mapping, so the exact original character can't be
# recovered after the fact, only guarded against going forward. These are
# the specific characters an LLM is known to reach for that fall outside
# WinAnsi; NFKD normalization below is the fallback for anything not in this
# table (it correctly leaves genuinely accented names like "Café Batata" or
# "Porto Brandão" alone, both of which *are* in WinAnsi).
_UNICODE_PDF_FALLBACKS = {
    "‑": "-",  # non-breaking hyphen
    "−": "-",  # minus sign
    " ": " ",  # thin space
    " ": " ",  # hair space
    " ": " ",  # figure space
    " ": " ",  # punctuation space
    " ": " ",  # narrow no-break space
    "​": "",  # zero-width space
    "﻿": "",  # zero-width no-break space / BOM
}


def _sanitize_for_pdf(text: str) -> str:
    """Replaces characters reportlab's base font can't render with a safe
    equivalent instead of letting them silently become a missing-glyph box.

    Only applied to write_up below, the one field in this module that's raw
    LLM prose rather than a tool's own data -- flight/hotel rows are mocked,
    attraction/restaurant names come from Geoapify (real place names, not
    free-form authoring), so write_up is the actual risk surface this
    guards.
    """
    if not text:
        return text
    for bad, replacement in _UNICODE_PDF_FALLBACKS.items():
        text = text.replace(bad, replacement)
    try:
        text.encode("cp1252")
        return text
    except UnicodeEncodeError:
        pass
    # Still something WinAnsi can't render (an emoji, a symbol with no
    # CP1252 equivalent) -- NFKD-decompose and drop what's left rather than
    # hand reportlab a character it can only draw as a box.
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("cp1252", errors="ignore").decode("cp1252")


def _table(rows: list[list[str]], col_widths: list[float] | None = None) -> Table:
    """One consistent table style used for every section below -- header
    row shaded in the app's own chrome blue, thin grid, small enough font
    to fit an airline name or a full forecast summary without wrapping
    awkwardly.
    """
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _TABLE_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9C9880")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _render_day_grouped_section(
    story: list,
    heading: str,
    items: list,
    empty_message: str,
    trailing_note: str | None = None,
) -> None:
    """Renders an Attractions- or Restaurants-shaped section (both models
    have .name, .category, and now .day, see schemas.py), grouped under a
    "Day N" subheading wherever the itinerary/food agent assigned one.

    day is best-effort (Attraction.day/Restaurant.day default to None when
    the agent wasn't confident, and assemble_trip_plan() clears any
    out-of-range value back to None too), so this only switches into
    day-grouped rendering once at least one item actually has a day.
    Otherwise it falls back to the original flat table -- a page with
    every attraction under a single "Unscheduled" heading would look
    broken, not honest, when really day assignment just isn't populated
    for this run.
    """
    story.append(Paragraph(heading, _HEADING_STYLE))
    if not items:
        story.append(Paragraph(empty_message, _STYLES["Normal"]))
        story.append(Spacer(1, 10))
        return

    scheduled: dict[int, list] = {}
    unscheduled: list = []
    for item in items:
        if item.day is not None:
            scheduled.setdefault(item.day, []).append(item)
        else:
            unscheduled.append(item)

    def _rows(group: list) -> list[list[str]]:
        rows = [["Name", "Category"]]
        for item in group:
            rows.append([item.name, item.category or "—"])
        return rows

    if scheduled:
        for day in sorted(scheduled):
            story.append(Paragraph(f"Day {day}", _SUBHEADING_STYLE))
            story.append(_table(_rows(scheduled[day]), col_widths=[3.5 * inch, 3 * inch]))
            story.append(Spacer(1, 6))
        if unscheduled:
            story.append(Paragraph("Unscheduled", _SUBHEADING_STYLE))
            story.append(_table(_rows(unscheduled), col_widths=[3.5 * inch, 3 * inch]))
    else:
        story.append(_table(_rows(items), col_widths=[3.5 * inch, 3 * inch]))

    if trailing_note:
        story.append(Spacer(1, 6))
        story.append(Paragraph(escape(trailing_note), _STYLES["Italic"]))
    story.append(Spacer(1, 10))


def build_trip_pdf(trip_plan: TripPlan, write_up: str) -> bytes:
    """Renders trip_plan plus the presenter agent's free-text write-up into
    a single PDF, returned as bytes ready for st.download_button.

    write_up is included as-is, unescaped structure aside -- it's already
    the same text shown in the chat, this just gives the traveler something
    to save and print instead of scrolling a chat window.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Trip Plan: {trip_plan.destination}",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    story = []

    story.append(Paragraph(escape(f"Trip Plan: {trip_plan.destination}"), _STYLES["Title"]))
    story.append(Paragraph(escape(f"{trip_plan.days}-day trip"), _STYLES["Normal"]))
    story.append(Spacer(1, 12))

    if trip_plan.flights:
        cheapest = min(
            (f for f in trip_plan.flights if f.price_usd is not None),
            key=lambda f: f.price_usd,
            default=None,
        )
        story.append(Paragraph("Flights", _HEADING_STYLE))
        # Plain strings, not escape()'d: Table cells render text literally
        # in reportlab, they don't run through Paragraph's XML-flavored
        # markup parser -- confirmed directly (escaping here previously
        # produced literal "-&gt;" on the page instead of "->"). escape()
        # is only correct for strings handed to Paragraph() below.
        rows = [["Airline", "Route", "Departure", "Price (USD)", "Source"]]
        for flight in trip_plan.flights:
            price = f"${flight.price_usd:,.2f}" if flight.price_usd is not None else "unknown"
            if flight is cheapest:
                price += " (lowest, used in budget)"
            rows.append(
                [
                    flight.airline or "—",
                    f"{flight.origin} -> {flight.destination}",
                    flight.departure_date,
                    price,
                    flight.source,
                ]
            )
        story.append(_table(rows))
        story.append(Spacer(1, 10))

    if trip_plan.hotel:
        hotel = trip_plan.hotel
        story.append(Paragraph("Hotel", _HEADING_STYLE))
        price = f"${hotel.price_per_night_usd:,.2f}/night" if hotel.price_per_night_usd is not None else "price unknown"
        rows = [
            ["Name", "City", "Check-in", "Check-out", "Price", "Source"],
            [hotel.name, hotel.city, hotel.check_in, hotel.check_out, price, hotel.source],
        ]
        story.append(_table(rows))
        story.append(Spacer(1, 10))

    _render_day_grouped_section(
        story,
        "Attractions",
        trip_plan.attractions,
        "No attractions available for this trip.",
    )

    _render_day_grouped_section(
        story,
        "Restaurants",
        trip_plan.restaurants,
        "No restaurants available for this trip.",
        trailing_note=(
            "Note: these are places nearby in the restaurant/cafe/fast-food "
            "categories, not a rated or curated list."
            if trip_plan.restaurants
            else None
        ),
    )

    story.append(Paragraph("Weather", _HEADING_STYLE))
    if trip_plan.weather:
        rows = [["Date", "Forecast"]]
        for report in trip_plan.weather:
            forecast = report.summary + (" (approximate)" if report.is_approximate else "")
            rows.append([report.date, forecast])
        story.append(_table(rows, col_widths=[1.5 * inch, 5 * inch]))
        if any(report.is_approximate for report in trip_plan.weather):
            story.append(Spacer(1, 6))
            story.append(
                Paragraph(
                    escape(
                        "Note: dates marked (approximate) are outside OpenWeatherMap's "
                        "5-day forecast window, so this is the closest available "
                        "forecast, not a real one for that date."
                    ),
                    _STYLES["Italic"],
                )
            )
    else:
        story.append(Paragraph("No weather forecast available for this trip.", _STYLES["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Budget (USD)", _HEADING_STYLE))
    budget = trip_plan.budget
    rows = [
        ["Category", "Amount"],
        ["Flights", f"${budget.flights_usd:,.2f}"],
        ["Hotel", f"${budget.hotel_usd:,.2f}"],
        ["Attractions", f"${budget.attractions_usd:,.2f}"],
        ["Restaurants", f"${budget.restaurants_usd:,.2f}"],
        ["Total", f"${budget.total_usd:,.2f}"],
    ]
    story.append(_table(rows, col_widths=[3 * inch, 2 * inch]))
    if budget.unpriced_categories:
        categories = ", ".join(budget.unpriced_categories)
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                escape(
                    f"Note: the total above does not include {categories}, "
                    "no price data was available for that category."
                ),
                _STYLES["Italic"],
            )
        )
    story.append(Spacer(1, 14))

    # trip_plan.research_gaps is the real, post-correction evaluation
    # (agent.py's assemble_trip_plan()/_evaluate_research_gaps()), the same
    # field app.py's sidebar renders under "Research gaps" -- this used to
    # be the *only* place a traveler saw it: this module had zero
    # references to research_gaps, so a downloaded PDF never carried the
    # signal at all, even though the presentation write-up below sometimes
    # reinvents its own informal version of it (that's the LLM noticing an
    # empty list on its own, not this real field, and it runs before
    # assemble_trip_plan()'s correction besides -- see CLAUDE.md's
    # day-by-day-write-up timing caveat). Only rendered when non-empty, same
    # as the sidebar.
    if trip_plan.research_gaps:
        story.append(Paragraph("Research Gaps", _HEADING_STYLE))
        for gap in trip_plan.research_gaps:
            story.append(Paragraph(f"• {escape(gap)}", _STYLES["Normal"]))
        story.append(Spacer(1, 14))

    story.append(Paragraph("Trip Summary", _HEADING_STYLE))
    for paragraph in write_up.split("\n\n"):
        stripped = _sanitize_for_pdf(paragraph.strip())
        if stripped:
            story.append(Paragraph(escape(stripped).replace("\n", "<br/>"), _STYLES["Normal"]))
            story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()
