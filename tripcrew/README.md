# tripcrew

An AI agent that plans multi-day trips end-to-end. Understands a goal,
decides which tools to call (flights, hotels, weather, attractions), and
asks for missing info instead of guessing.

Give it something like "plan a 3-day trip to Paris" and it has to figure
out what that actually requires: an origin city and dates it wasn't given,
a sequence of tool calls it has to choose for itself, and a final plan that
holds together (flights, a hotel, a few attractions, weather, and a budget
that's actually the sum of what the tools returned, not a number an LLM
made up). That loop, understand the goal, plan the steps, pick and use
tools, check the results, answer, is the actual point of the project. A
chatbot that already knows the steps isn't demonstrating it.

## Current state

The planner works end to end on mocked flight and hotel data. Four agents,
not the five originally sketched, food research is deferred until its tool
exists (see `docs/architecture.rst`): an intake agent that asks for
whatever's missing (origin city, dates, budget) before anything else runs,
an itinerary agent that pulls real attractions and weather, a consolidator
that builds the final plan and calls a real tool to compute the budget
total instead of stating one itself, and a presenter that writes it up. `tripcrew/app.py` is a working
Streamlit chat, not a skeleton, it runs a cheap intake-only check first and
only kicks off the full crew once it has enough to work with.

Weather and attractions call real APIs (OpenWeatherMap, Geoapify).
Flights and hotels are mocked on purpose, not by oversight, because the
APIs with real live pricing gate access behind a business-partner approval
process that doesn't clear on a reasonable timeline. See
`docs/architecture.rst` for the full reasoning and what the realistic path
forward looks like.

## Where this is headed

The plan, in rough order:

1. Basic error handling for tool and API failures, done. A missing weather
   result or a failed attraction lookup degrades to "not available" instead
   of raising, the budget flags any category it couldn't price instead of
   quietly counting it as free, and the consolidation agent now calls a
   real tool to compute the total instead of writing one itself. Full
   reasoning in `docs/architecture.rst`.
2. The food research agent and its tool, once it's worth the second
   Geoapify integration.
3. Exporting the finished itinerary to PDF.
4. A follow-up chatbot that answers questions about the generated plan,
   now planned as a knowledge graph over the `TripPlan` object rather than
   a RAG pipeline, since the data's already structured and graph traversal
   avoids a class of hallucination risk an LLM-generated answer wouldn't.
   Explicitly a separate, later phase.
5. Testing, properly. `evaluation/README.md` lays out why promptfoo and
   deepeval are scoped to different layers (agent behavior versus answer
   quality) instead of picking one and using it for both.

Nothing above is committed to landing in that exact order. It's the
intention, written down so it doesn't drift, not a promise about what's
finished by any particular date.

## Setup

See `docs/getting-started.rst` for the full walkthrough. Short version:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in real keys
streamlit run tripcrew/app.py
```

## Docs

Full documentation lives under `docs/` (Sphinx, set up for Read the Docs,
not yet confirmed live). Also skeletal right now, built alongside the code
instead of after it.
