Architecture
============

This page is a skeleton. Real architecture diagrams come once the planning
loop and clarification flow are actually built -- documenting a design
that's still moving isn't worth much yet. What follows is the current
intent, not a finished design.

Five-role sequential crew
---------------------------

Originally this was a single agent with four tools, reasoning step by step
through its own tool calls. That was a defensible read of the project
brief's own language, but it's not what's being built now: the actual
requirement is a multi-agent crew, specifically five roles, run under
CrewAI's ``Process.sequential`` with each task's output passed as context
to the next, the same pattern the code-review-crew project used for its
verifier task.

The five roles: an intake/coordinator agent that owns the clarification
loop (asking for missing origin city, dates, or budget) plus flights and
hotels, since nothing else can usefully run until logistics are settled.
An itinerary research agent that owns attractions and weather, since
weather should influence how attractions get sequenced across days. A food
research agent that owns restaurants and cafes, covered below. A
consolidation agent that merges everything into ``TripPlan``, and calls
the Budget Estimator tool (``estimate_budget()``) to get
``Budget.total_usd`` rather than stating one itself, see "Error handling
for tool failures" below for how that came to be its one tool. A
presentation agent that formats the finished plan for the user.

Sequential over hierarchical on purpose: CrewAI also offers
``Process.hierarchical``, where a manager agent dynamically delegates to
workers. That's a reasonable shape too, but it stacks a second unreliable
decision, the manager's delegation choices, on top of per-task reliability
problems already documented on the code-review-crew project (a verifier
letting a factually wrong finding through, the same file producing
different findings run to run). Sequential is more predictable and easier
to debug when something goes wrong, which matters more here than looking
more autonomous.

Clarification loop
---------------------

Implemented as two separate crews rather than one crew that pauses
mid-run. ``build_intake_crew()`` runs intake by itself and checks the
resulting ``TripPlan``'s ``open_questions``. If it's non-empty,
``app.py`` shows those questions and waits for the next chat message,
accumulating the whole conversation into a single growing string passed
back in as ``{request}`` next time. Once ``open_questions`` comes back
empty, ``app.py`` calls ``build_crew()`` and runs the real five-agent
pipeline.

This works because Streamlit already reruns the whole script on every
new message with ``session_state`` persisting between runs, so "wait for
the next message" doesn't need anything special from CrewAI itself, which
has no built-in way to pause a running task for a web request/response
cycle. The tradeoff: once the full crew runs, its own intake task runs
again from scratch rather than reusing the already-satisfied draft, one
redundant LLM call per plan, not a correctness problem, just not the most
efficient shape. Worth revisiting if it turns out to matter.

Food research
----------------

Built and wired in. ``tripcrew/tools/restaurants.py`` reuses Geoapify's
``categories`` filter, same API key and same request/response shape as
``tripcrew/tools/attractions.py``, filtered to ``catering.restaurant``,
``catering.cafe``, and ``catering.fast_food`` instead of landmark
categories -- confirmed against Geoapify's own docs before building it,
same as the original attractions integration was.

One real design difference from attractions, not an oversight: there's no
notability filter here. ``get_attractions()`` restricts its first request
to Geoapify's ``wiki_and_media`` condition, a real Wikipedia/Wikidata link,
because a genuine landmark usually has one. A good neighborhood restaurant
almost never does, and Geoapify's Places API doesn't carry a rating,
popularity, or price-level field for catering places any more than it does
for attractions, checked directly against the response shape before
deciding this. Applying ``wiki_and_media`` here would come back near-empty
for exactly the places worth listing and just fall through to an
unfiltered search anyway, defeating the point of having it. So
``get_restaurants()`` makes a single category-filtered request and returns
what's nearby, and every downstream consumer, the food task's own
description, the presentation task, ``followup.py``, ``pdf_export.py``,
says plainly that this is a nearby-places list, not a rated or curated
one. If real curation matters later, that's a fresh evaluation against
something with actual ratings (Foursquare's paid tier, say), not a filter
bolted onto Geoapify.

``estimate_budget()`` takes ``restaurants`` as a required argument now,
same shape as flights/hotel/attractions, and ``Budget`` has a
``restaurants_usd`` field. Geoapify doesn't return cost data for catering
places any more than it does for attractions, so a real run flags
``"restaurants"`` in ``unpriced_categories`` every time, same honest gap
attractions already has.

Why flights and hotels are mocked
------------------------------------

Real live-price flight and hotel APIs (Skyscanner, Kiwi, Booking.com) gate
access behind a business-partner approval process with no published
timeline -- not workable against a deadline. Amadeus's self-service sandbox
is the realistic path if genuine API integration happens later, but its
free tier returns test data, not live prices, so even that wouldn't be live
pricing. For now, ``tripcrew/tools/flights.py`` and ``tripcrew/tools/hotels.py``
return mocked data shaped exactly like a real response, so swapping the
implementation later doesn't require touching anything that calls them.

Error handling for tool failures
------------------------------------

CrewAI already catches an exception raised inside an ``@tool``-decorated
function. ``ToolUsage._use()`` wraps the actual call in a try/except,
retries a few times, then hands the agent an error string and moves on. So
a raw ``raise`` was never going to crash ``crew.kickoff()``. What it did
mean: the agent burned retries on a permanent failure (a missing API key
isn't going to succeed on attempt two), got handed a raw error string
instead of a clean signal, and nothing told it what an empty result should
mean, so it had every incentive to paper over the gap with a plausible
guess.

``get_weather`` now returns ``None`` and ``get_attractions`` returns ``[]``
instead of raising, for the same failure causes as before (missing API key,
geocoding failure, the HTTP request itself failing). Both already fit the
schema without a new field, ``TripPlan.weather`` and ``TripPlan.attractions``
are lists, so a missing result just means a shorter list. The itinerary
task's description was updated to say plainly that an empty result means
"not available," not license to invent one.

``estimate_budget()`` had a quieter version of the same problem: a missing
price (``price_usd`` or ``estimated_cost_usd`` being ``None``) was treated
as ``price or 0``, silently counting "we don't know" as "free." Attractions
hit this on every run, Geoapify never returns cost data, so
``attractions_usd`` was always 0 with nothing flagging it. ``Budget`` now
has ``unpriced_categories``, populated by ``estimate_budget()``, and the
presentation task is told to say the total excludes those categories rather
than present it as complete.

Flights and hotels don't need any of this, they're mocked, pure in-memory
generation with no I/O to fail.

The consolidation task used to have the same problem in a quieter form:
``output_pydantic=TripPlan`` and no tools meant ``Budget.total_usd`` in the
final plan was written by the LLM from context, not computed at all,
despite ``estimate_budget()`` already existing and being imported into
``agent.py``. Nothing ever called it. That's now fixed: ``estimate_budget``
is a real ``@tool``, ``consolidation_agent`` has it as its one tool, and
the consolidation task's description tells it to call the tool with the
gathered flight, hotel, and attraction data and use exactly what comes
back, not to compute or restate a total itself.

One thing worth knowing if this tool gets touched again: CrewAI's tool
layer hands the underlying function whatever the LLM's tool call JSON
deserializes to, plain dicts, not ``Flight``/``Hotel``/``Attraction``
instances, even though the ``args_schema`` built from the function's type
hints describes that nested shape. Confirmed by calling
``estimate_budget.run()`` directly and hitting an ``AttributeError`` on a
dict. ``estimate_budget()`` now coerces its inputs with
``Model.model_validate(...)`` at the top instead of assuming the type hints
are enforced automatically.

Consolidation can't be trusted to restate research output
--------------------------------------------------------------

``Budget.total_usd`` wasn't the only value the consolidation task's LLM was
trusted to restate rather than copy. ``output_pydantic=TripPlan`` on that
task means its LLM authors the *whole* plan, including
``attractions``, ``weather``, and ``restaurants``, from the itinerary and
food tasks' context, not by mechanically forwarding those tasks' own
output. A real London run showed exactly what that risks: the weather
table came back with the summary "Light rain, ~22C (approximate)
(approximate)", a corrupted duplicate that ``get_weather()`` itself never
produces (confirmed by reading its actual return value, a plain
``f"{description}, {temp}C"`` string). The corruption was introduced
entirely by the consolidation task's own retelling.

Fixed the same way ``Budget.total_usd`` was: stop asking the LLM to
restate a value that already exists elsewhere as real data.
``build_itinerary_task()`` and ``build_food_task()`` now have their own
``output_pydantic`` types, ``ItineraryResearch`` and ``FoodResearch``
(``tripcrew/schemas.py``), so ``get_attractions()``, ``get_weather()``, and
``get_restaurants()``'s actual return values exist as structured task
output in their own right, not only as prose the consolidation task has to
re-read. ``agent.py``'s ``assemble_trip_plan()`` is the function that
actually uses this: called on the finished crew's result, it finds the
consolidation task's ``TripPlan`` the same way ``app.py`` always did (by
``isinstance`` on ``tasks_output``, not a fixed list index), then
overwrites its ``attractions``, ``weather``, and ``restaurants`` with the
itinerary and food tasks' real structured output before anything (the
sidebar, the PDF, the follow-up chatbot) sees it. ``app.py`` calls
``assemble_trip_plan()`` instead of reading the consolidation task's
``TripPlan`` directly now.

The consolidation task still produces its own (unused) version of these
three fields, since telling it to skip them entirely bought nothing:
``expected_output`` still describes a complete plan, and the real values
get substituted in regardless of what it writes there. Its budget,
flights, hotel, destination, and open_questions are still trusted as its
own output, only the three research-derived list fields get the
override, and only because a real bug proved the restating step corrupts
them.

PDF export
-------------

``tripcrew/pdf_export.py`` renders a finished plan to a downloadable PDF,
offered as a sidebar button once the full crew finishes. It reads the same
consolidated ``TripPlan`` the sidebar itself now shows (see "Reflects the
final consolidated plan" in ``app.py``'s ``render_sidebar()`` docstring),
not a re-parsed copy of the presenter's free-text write-up, and every
number on the page comes from ``TripPlan.budget``, the same groundedness
rule ``estimate_budget()`` follows above: this module never computes a
total, sum, or price of its own.

It isn't a CrewAI ``@tool`` and doesn't live under ``tripcrew/tools/``,
nothing here is called by an agent, ``app.py`` calls ``build_trip_pdf()``
directly. Built with reportlab's Platypus layer (``SimpleDocTemplate`` plus
``Paragraph``/``Table`` flowables), pure Python, no system dependency like
a headless browser or ``wkhtmltopdf``. One real bug caught while building
this, worth remembering if the module gets touched again: reportlab's
``Table`` renders plain string cells literally, it does not run them
through the XML-flavored markup parser that ``Paragraph`` uses for ``<``,
``>``, and ``&``. Escaping table-cell text (a flight route formatted as
``"JFK -> LIS"``, say) produced a literal ``-&gt;`` on the rendered page
instead of ``->``. Caught by rendering an actual sample and reading it back
with ``pypdf``, not by the build succeeding without raising, since an
unescaped ``<`` or ``&`` reaching a ``Paragraph`` *would* raise, which is
what made the bug easy to miss at first: escaping felt like the safe
default everywhere.

Follow-up chatbot
--------------------

``tripcrew/followup.py`` answers questions about a finished plan once
``app.py`` detects one exists (``st.session_state.trip_write_up`` set).
The next chat message stops feeding ``build_intake_crew()`` entirely and
goes to ``answer_trip_question()`` instead -- "Start over" in the sidebar
is the explicit, only way back to planning a different trip.

This ended up simpler than the originally sketched knowledge-graph design
above once it came time to actually build it. ``TripPlan`` already has a
small, fixed set of top-level fields (flights, hotel, attractions,
weather, budget), so a real graph with nodes and edges would have been
structure for its own sake, five key lookups don't need traversal
machinery. What's kept from the original idea is the reasoning behind it:
one LLM call classifies which of those five fields a question is about
(``output_pydantic=TripQuestionIntent``, same pattern as every other
structured call in this project), and plain Python answers by reading that
field directly off ``TripPlan``. The LLM's output can never contain a
fact, only a pointer to where a fact already is, that's what actually
avoids the RAG-style hallucination risk (an answer stating a detail that
sounds plausible but isn't in the plan), not the presence or absence of a
graph data structure specifically.

The one place classification still touches a real value directly: a
weather question about a specific day ("day 2", "the first day") needs a
resolved date to look up. The intent task's description lists the trip's
actual forecast dates and tells the model to pick one of those exactly, or
leave the field empty rather than guess, same "treat missing as missing,
don't invent" rule ``get_weather()`` and ``get_attractions()`` already
follow.

Not yet designed
-------------------

- promptfoo and deepeval evaluation suites (see
  ``evaluation/README.md`` for the intended split between them). Nothing
  else is currently deferred, the five-role crew described above is fully
  built and wired in.
