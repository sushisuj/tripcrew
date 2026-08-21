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
_TABLE_HEADER_BG = colors.HexColor("#6E8CC7")


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

    story.append(Paragraph("Attractions", _HEADING_STYLE))
    if trip_plan.attractions:
        rows = [["Name", "Category"]]
        for attraction in trip_plan.attractions:
            rows.append([attraction.name, attraction.category or "—"])
        story.append(_table(rows, col_widths=[3.5 * inch, 3 * inch]))
    else:
        story.append(Paragraph("No attractions available for this trip.", _STYLES["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Weather", _HEADING_STYLE))
    if trip_plan.weather:
        rows = [["Date", "Forecast"]]
        for report in trip_plan.weather:
            rows.append([report.date, report.summary])
        story.append(_table(rows, col_widths=[1.5 * inch, 5 * inch]))
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

    story.append(Paragraph("Trip Summary", _HEADING_STYLE))
    for paragraph in write_up.split("\n\n"):
        stripped = paragraph.strip()
        if stripped:
            story.append(Paragraph(escape(stripped).replace("\n", "<br/>"), _STYLES["Normal"]))
            story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()
