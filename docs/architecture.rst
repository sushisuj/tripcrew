Architecture
============

This page is a skeleton. Real architecture diagrams come once the planning
loop and clarification flow are actually built -- documenting a design
that's still moving isn't worth much yet. What follows is the current
intent, not a finished design.

.. contents:: On this page
   :local:
   :depth: 1

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

Day-by-day sequencing
-------------------------

``Attraction`` and ``Restaurant`` both carry a ``day`` field (1-indexed,
``schemas.py``), turning "3-day trip" from a label on ``TripPlan.days``
into something the itinerary actually structures around. Before this,
sequencing across days only ever existed as prose the presentation agent
wrote, using the weather context in its own context window, nothing
downstream (the PDF, the follow-up chatbot) could rely on which day
anything belonged to.

Unlike the fields ``assemble_trip_plan()`` overwrites (see above), ``day``
isn't a tool's raw output being restated, ``get_attractions()`` and
``get_restaurants()`` don't know about days at all. It's the itinerary and
food agents' own reasoning, informed by the weather forecast for
attractions and a plain even spread for restaurants, assigned once as part
of authoring ``ItineraryResearch``/``FoodResearch``. That makes it a
genuinely agent-authored value, not a groundedness violation the way
restating an already-known fact would be, but it's still a number a model
can get wrong the way any generated output can. ``assemble_trip_plan()``
clears any day outside ``1..TripPlan.days`` back to ``None`` rather than
show an impossible day on the finished plan, the same "verify what's
checkable, even from an agent's own reasoning" instinct as everything else
this project won't take on faith.

``pdf_export.py`` groups attractions and restaurants under a "Day N"
heading once at least one item has a day set, with anything left unset
gathered under an "Unscheduled" heading below the day groups. If nothing
has a day at all, it falls back to the original flat table rather than a
page showing everything under one "Unscheduled" heading, day assignment
being unpopulated for a given run should look like the feature not firing,
not like the trip is disorganized.

One real limitation, not hidden: the presentation task's write-up reads
the consolidation task's own copy of ``attractions``/``restaurants``, not
the corrected one ``assemble_trip_plan()`` produces, because that
correction only runs after ``crew.kickoff()`` returns and the presenter
has already finished by then. So the write-up's day-by-day framing can
occasionally disagree with the PDF's tables in a way that's hard to fully
close without restructuring when ``assemble_trip_plan()`` runs relative to
presentation. Not a new gap, the write-up was always the LLM's own
retelling rather than grounded data. The PDF's tables are the source of
truth, the write-up is presentation.

Evaluating and reacting to empty or thin research results
----------------------------------------------------------

A real London run exposed a gap this section closes: ``get_attractions()``
came back empty (a since-fixed notability bug, see the section above this
one), and nothing anywhere reacted to that. The empty list just passed
straight through ``ItineraryResearch``, ``assemble_trip_plan()``, and the
presenter, and came out the other end as a write-up that quietly described
a London trip with no attractions in it, no different in tone from a trip
where attractions genuinely weren't asked about. The tools already had an
honest way to report "not available" (an empty list), what was missing was
anything checking that result and doing something about it.

The fix has two halves, react and evaluate, at two different points in the
pipeline.

React, inside the tool itself: ``get_attractions()`` and
``get_restaurants()`` (``tripcrew/tools/``) both try one wider search before
giving up. ``get_attractions()`` already fell back from a notability-filtered
search to an unfiltered one for the same destination (see above); now, if
even that unfiltered search comes back empty, it tries once more at
``WIDE_SEARCH_RADIUS_METERS`` (25km, up from the normal 10km).
``get_restaurants()`` has no notability condition to fall back from, but
gets the same radius-widening react: one retry at 25km if the normal-radius
search is empty. Both are bounded to a single retry on purpose, this widens
the search once, it doesn't loop trying to force a result out of a
destination that may genuinely not have one.

Evaluate, once research is back: ``agent.py``'s ``assemble_trip_plan()``
calls ``_evaluate_research_gaps()`` after substituting the real
attractions/restaurants/weather (see "Consolidation can't be trusted..."
above) and clamping ``day`` values. It checks the real, final lists, not
what the consolidation task guessed, and flags a category in the new
``TripPlan.research_gaps`` field whenever it's empty, or -- past
``THIN_RESEARCH_THRESHOLD`` -- has only a single result. One attraction for
a whole multi-day trip isn't meaningfully different from zero for planning
purposes, the same "don't let a number imply completeness it doesn't have"
rule ``Budget.unpriced_categories`` already applies to price data, applied
here to a count. Weather is only checked for being empty outright, not
scored against the threshold, ``WeatherReport.is_approximate`` already
carries the finer-grained honesty signal for weather.

``research_gaps`` is computed fresh every time, never trusted from any
task's own output, same reasoning as ``attractions``/``weather``/
``restaurants`` themselves: a count is a checkable fact once the real
research is in hand. ``app.py``'s sidebar shows it under a "Research gaps"
heading once the full crew finishes, the reliable place a traveler actually
sees it. The presentation task is told to mention it in the write-up too,
but reads the consolidation task's own (always-empty, at that point in the
chain) copy of the field, the same timing limitation "Day-by-day
sequencing" above documents for ``day``: the real evaluation only happens
after ``crew.kickoff()`` returns, once the presenter has already run.

Running itinerary and food research concurrently
--------------------------------------------------

``Process.sequential`` still governs the task list's order, but it's no
longer strictly one task after another top to bottom. Itinerary research
and food research (``build_itinerary_task()``/``build_food_task()`` and
their ``_from_plan`` counterparts, ``agent.py``) both run with
``async_execution=True`` now, so they execute concurrently rather than one
waiting on the other to finish.

This is the one genuinely dynamic sequencing decision in the crew, and
it's still code deciding, not an LLM guessing at a schedule: which tasks
can run in parallel is fixed by their actual data dependencies. Both tasks
only read the intake research's output (destination, days, dates), neither
reads the other's, confirmed directly off each task's own ``context``
parameter rather than assumed from what the roles sound like they'd need.

Confirmed safe by reading CrewAI's own source (the installed ``crewai``
package's ``crew.py``), not assumed from its docs. ``_execute_tasks()``
kicks off an ``async_execution=True`` task as a background thread and
Future, then continues immediately to the next task in the list; when it
reaches the next non-async task, it drains any pending futures first,
blocking on each in the order they were added, before running the sync
task. A downstream task's ``context=[...]`` is resolved via
``_get_context()``, which reads ``.output`` straight off the referenced
Task objects, already set by the time a future resolves, not off a
positional accumulator. So it doesn't matter which of the two concurrent
tasks actually finishes first, the consolidation task's context is
correct either way.

One real consequence, not free: ``task.py``'s ``_execute_core()``, which
fires ``crew.task_callback(self.output)``, runs inside the background
thread for an async task. That means ``task_callback`` can now fire from
a non-main thread, and in whichever order the two concurrent tasks
actually complete, not necessarily the order they appear in
``build_crew()``'s task list. See "Surfacing which stage just finished"
below for how ``app.py`` and ``agent.py`` adapted to that.

Surfacing which stage just finished
--------------------------------------

Before this, ``app.py`` tracked planning progress by counting
``task_callback`` calls against a fixed list of stage labels, one label
per position, since every task used to finish in list order. That
assumption broke the moment itinerary and food research started running
concurrently (see above): the two can now finish in either order, and
whichever one wins fires first, so counting by position could attach the
wrong label to a finished stage.

``agent.py``'s ``stage_label_for()`` replaces counting with a lookup: it
matches a finished task's ``task_output.pydantic`` against its real type
(``ItineraryResearch``, ``FoodResearch``, ``TripPlan``, listed in
``STAGE_LABELS_BY_OUTPUT_TYPE``) rather than trusting when it arrived. The
presentation task has no ``output_pydantic`` (free text), so its
``task_output.pydantic`` is always ``None``, checked for explicitly rather
than added as a fourth ``(type, label)`` pair. ``PLANNING_STAGE_LABELS``
is the fixed reading order the UI actually renders in (research, then
consolidation, then the write-up), independent of which order the two
concurrent research tasks happened to complete in on a given run.

The other consequence, mentioned above: ``task_callback`` can now fire
from a background thread. Streamlit widget calls (``status.write()`` and
the like) from a background thread are unsafe, they're missing the
``ScriptRunContext`` a widget call needs, confirmed by reading Streamlit's
own execution model, not assumed from a stack trace. So ``app.py``'s
callback, ``mark_stage_done()``, never touches ``status`` or any other
Streamlit widget directly. It only appends to a plain list and a plain
dict, guarded by a ``threading.Lock`` since the two concurrent tasks can
call it from two different threads close to the same moment. Every actual
widget write (the checkmarks, the reasoning expander) happens after
``kickoff()`` returns, back on the main thread, reading what
``mark_stage_done()`` recorded. ``build_crew()``'s own ``task_callback``
parameter still isn't wrapped in a try/except, that responsibility
belongs to the callback passed in, a UI update failing should never be
able to take the actual crew run down with it, which is also why
``mark_stage_done()`` swallows its own exceptions internally.

Surfacing the agent's reasoning, not just which stage finished
------------------------------------------------------------------

Every stage checkmark said a task finished, nothing said why the agent
did what it did. ``agent.py``'s ``extract_reasoning()`` and
``reasoning_entry_for()`` close that gap, and ``app.py`` shows the result
in a collapsed "How the agent got here" expander under the finished
write-up.

Not built from ``TaskOutput.raw``. For a task with ``output_pydantic`` set
(all three of the research/consolidation stages), ``.raw`` is just that
structured output restated as JSON, confirmed by reading ``crewai``'s
``task.py``: ``_execute_core()`` does ``raw = result.model_dump_json()``
once the executor's result is already a pydantic model. That's the same
data a second time in a different format, not the agent's reasoning about
how it got there. ``TaskOutput.messages`` is where the real reasoning
survives: the actual conversation transcript for that task, confirmed via
``agent/utils.py``'s ``save_last_messages()``, including any free text the
agent wrote before or between tool calls, the tool calls themselves, and
the tools' own results.

``extract_reasoning()`` keeps only the assistant role's own text content,
in call order, skipping messages with no text (a pure tool call or a
tool's result message isn't the agent's reasoning, it's a mechanical
step). ``reasoning_entry_for()`` pairs that with ``stage_label_for()`` so
a label and its own reasoning travel together as one unit, calling the
two separately risked pairing one task's label with a different task's
reasoning once itinerary and food research started finishing in whichever
order they actually complete.

This is unverified by design, the same caveat this project already
applies to the presentation task's write-up: it's the agent's own
retelling of its process, shown for transparency, not trusted as fact the
way ``TripPlan``'s own fields are (those come from tools, or from
``assemble_trip_plan()``'s own checkable logic). It stays outside
``TripPlan`` entirely, both in the code (``app.py`` keeps it in its own
``reasoning_trail`` list, attached per-message in
``st.session_state.messages``, never merged into the plan) and in how
it's presented (collapsed, explicitly labeled "unverified"). Don't fold
it into a schema meant to be trustworthy, that would erase the exact
distinction this feature exists to preserve.

Live-judge evaluation suite
-------------------------------

A plain ``pytest`` assertion can check that a field equals an expected
value. It can't check whether a sentence in the presentation task's
write-up actually reflects what's in the real ``TripPlan``, the exact gap
the corrupted-weather-summary bug above shows can go silently wrong. That
gap is what ``tripcrew/evals/`` and ``tests/evals/`` close, using
`deepeval <https://github.com/confident-ai/deepeval>`_ rather than
promptfoo: this project already tests with pytest, and a deepeval suite
stays inside that same runner and config format instead of adding a
second one. ``evaluation/README.md``'s original plan to split coverage
between promptfoo and deepeval is stale now, only deepeval got built.

``tripcrew/evals/judge_llm.py``'s ``TripCrewJudgeLLM`` is the piece that
makes this affordable to run: deepeval's built-in metrics need an LLM to
act as judge, and default to requiring a real OpenAI account and key.
This project already has one LLM configured (``agent.py``'s
``build_llm()``, pointed at NVIDIA NIM, not OpenAI directly, see "Why
flights and hotels are mocked" section's neighbor for the actual reasoning
on that swap), so ``TripCrewJudgeLLM`` implements deepeval's
``DeepEvalBaseLLM`` interface (``load_model()``, ``generate()``,
``a_generate()``, ``get_model_name()``, confirmed against deepeval's own
source) by wrapping that same object, instead of asking for a second,
unrelated API key just to run evals. One thing worth knowing if this gets
touched: ``crewai.LLM(...)`` is a factory, not a concrete class,
confirmed directly, ``build_llm()``'s actual return type is
``crewai.llms.providers.openai.completion.OpenAICompletion``, a
``crewai.llms.base_llm.BaseLLM`` subclass, not an instance of
``crewai.llm.LLM`` itself. ``TripCrewJudgeLLM`` and its tests check
against ``BaseLLM``, the real common ancestor and the actual interface
(``.call()``/``.acall()``) ``generate()``/``a_generate()`` depend on.

``tripcrew/evals/context.py``'s ``trip_plan_context()`` turns a
``TripPlan`` into one string per checkable fact (each flight, the hotel,
each attraction with its day, each restaurant with its day and a note
that it's not a rated list, each weather entry with its approximate flag,
the budget line, unpriced categories if any, research gaps if any), the
grounding data a faithfulness/hallucination judge checks a write-up
against.

``tests/evals/test_writeup_groundedness.py`` has two cases: one write-up
faithful to a real Lisbon ``TripPlan``, and one that fabricates a visit to
the Louvre, a landmark the plan never produced and that isn't even in the
right city. Not an exhaustive suite, more fabrication shapes (a dropped
research gap, a misstated price) are real future work, not padded out
here just to inflate test count. Both ``FaithfulnessMetric`` and
``HallucinationMetric`` run against the faithful case; only
``FaithfulnessMetric`` against the fabrication, checked with a direct
``metric.measure()``/``metric.score`` assertion rather than
``assert_test()`` so the failure message can show the judge's own
reasoning. The two metrics want the same context data under different
``LLMTestCase`` fields, confirmed against deepeval's source
(``_required_params`` on each metric class): ``FaithfulnessMetric`` needs
``retrieval_context``, ``HallucinationMetric`` needs ``context``, both set
to the same ``trip_plan_context()`` output on the combined test case, not
a typo. ``HallucinationMetric``'s threshold direction changed in a recent
deepeval release, deepeval prints its own deprecation notice confirming
it live: 1 is a pass, 0 is a failure, threshold is the minimum passing
score now, the same direction every other deepeval metric already used,
not the older "threshold = maximum allowed violation rate" reading a
low number like 0.3 would imply.

These two tests are marked ``eval`` (``pytest.ini``) and excluded from a
plain ``pytest`` run (``addopts = -m "not eval"``, confirmed to actually
filter rather than silently select zero tests, and confirmed that
``pytest -m eval`` on the command line correctly overrides that default
rather than being ignored). Every other test in this project mocks its
network calls; these two deliberately don't, they call the real judge
model over the network, so they're opt-in, run with ``pytest -m eval``.
They need the same ``.env`` this project already asks for
(``OPENAI_API_KEY``/``OPENAI_API_BASE``), nothing extra.

Installing ``deepeval`` pulls in a newer ``posthog`` than ``chromadb`` (a
``crewai`` dependency) wants, pip prints a resolver conflict warning on
install. Confirmed harmless by direct testing, not just by the warning
going away: ``crewai``, ``chromadb``, and ``tripcrew.agent`` all still
import and behave correctly despite it. Not force-pinned to silence the
warning, that risks breaking either package's real behavior without a way
to verify both configurations live, documented here instead, honestly,
the same as every other known wrinkle in this project.

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

- A real Amadeus sandbox integration for flights and hotels. Mocked data
  is explicitly fine for now (see "Why flights and hotels are mocked"
  above), this is future work, not a gap to quietly patch.
- promptfoo. Only deepeval got built (see "Live-judge evaluation suite"
  above for why it was chosen over promptfoo); ``evaluation/README.md``'s
  original split between the two no longer describes the real setup.
- A broader live-judge eval suite. ``tests/evals/test_writeup_groundedness.py``
  covers two cases today, more fabrication shapes, a dropped
  ``research_gap``, a misstated price, are real future work. Nothing else
  is currently deferred, the five-role crew described above, its
  concurrent research tasks, its reasoning trail, and its eval suite are
  all fully built and wired in.
