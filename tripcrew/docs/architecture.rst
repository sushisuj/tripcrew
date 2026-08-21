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
research agent, covered below. A consolidation agent that merges
everything into ``TripPlan``, and calls the Budget Estimator tool
(``estimate_budget()``) to get ``Budget.total_usd`` rather than stating one
itself, see "Error handling for tool failures" below for how that came to
be its one tool. A presentation agent that formats the finished plan for
the user.

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
empty, ``app.py`` calls ``build_crew()`` and runs the real four-agent
pipeline.

This works because Streamlit already reruns the whole script on every
new message with ``session_state`` persisting between runs, so "wait for
the next message" doesn't need anything special from CrewAI itself, which
has no built-in way to pause a running task for a web request/response
cycle. The tradeoff: once the full crew runs, its own intake task runs
again from scratch rather than reusing the already-satisfied draft, one
redundant LLM call per plan, not a correctness problem, just not the most
efficient shape. Worth revisiting if it turns out to matter.

Food research is deferred
----------------------------

The food/restaurant research agent is part of the design but not wired
into the crew yet. It depends on a food-search tool that hasn't been
built. The plan is to reuse Geoapify's ``categories`` filter, same API key
and same pattern as ``tripcrew/tools/attractions.py``, just filtered to
restaurants and cafes instead of landmarks, so it's a small addition when
it happens, not a new integration. Until then the crew runs with four
roles, not five.

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

Not yet designed
-------------------

- The food research agent and its tool, deferred as described above
- The follow-up chatbot, now planned as a knowledge graph over the
  generated ``TripPlan`` rather than a RAG pipeline. ``TripPlan`` is
  already structured pydantic output, so building a graph from it is data
  transformation, not the slow LLM entity extraction that killed the
  original knowledge-graph project on Constellate. Answering by graph
  traversal instead of LLM generation also removes a class of hallucination
  risk that a RAG answer wouldn't. Explicitly a separate, later phase, not
  part of the planner itself.
