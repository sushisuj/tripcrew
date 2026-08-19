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
everything into ``TripPlan`` and is where ``Budget.recompute()`` actually
gets called, not any agent's stated total. A presentation agent that
formats the finished plan for the user.

Sequential over hierarchical on purpose: CrewAI also offers
``Process.hierarchical``, where a manager agent dynamically delegates to
workers. That's a reasonable shape too, but it stacks a second unreliable
decision, the manager's delegation choices, on top of per-task reliability
problems already documented on the code-review-crew project (a verifier
letting a factually wrong finding through, the same file producing
different findings run to run). Sequential is more predictable and easier
to debug when something goes wrong, which matters more here than looking
more autonomous.

Food research is deferred
----------------------------

The food/restaurant research agent is part of the design but not wired
into the crew yet. It depends on a food-search tool that hasn't been
built. The plan is to reuse OpenTripMap's ``kinds`` filter, same API key
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

Not yet designed
-------------------

- The multi-turn clarification loop itself (asking for origin city, dates,
  or budget when missing, then resuming with the answer). The intake agent
  owns this conceptually; it isn't implemented.
- Error handling for tool/API failures beyond raising
- The PDF export step
- The food research agent and its tool, deferred as described above
- The follow-up chatbot, now planned as a knowledge graph over the
  generated ``TripPlan`` rather than a RAG pipeline. ``TripPlan`` is
  already structured pydantic output, so building a graph from it is data
  transformation, not the slow LLM entity extraction that killed the
  original knowledge-graph project on Constellate. Answering by graph
  traversal instead of LLM generation also removes a class of hallucination
  risk that a RAG answer wouldn't. Explicitly a separate, later phase, not
  part of the planner itself.
