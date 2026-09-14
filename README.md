# tripcrew

An AI agent that plans multi-day trips end-to-end. Understands a goal,
decides which tools to call (flights, hotels, weather, attractions,
restaurants), and asks for missing info instead of guessing.

Give it something like "plan a 3-day trip to Paris" and it has to figure
out what that actually requires: an origin city and dates it wasn't given,
a sequence of tool calls it has to choose for itself, and a final plan that
holds together (flights, a hotel, a few attractions and restaurants,
weather, and a budget that's actually the sum of what the tools returned,
not a number an LLM made up). That loop, understand the goal, plan the
steps, pick and use tools, check the results, answer, is the actual point
of the project. A chatbot that already knows the steps isn't demonstrating
it.

## Current state

The planner works end to end on mocked flight and hotel data, with all
five originally sketched agents wired in and a fair amount built past that
original sketch (see `docs/architecture.rst` for the full reasoning behind
each decision below): an intake agent that asks for whatever's missing
(origin city, dates, budget) before anything else runs, an itinerary agent
that pulls real attractions and weather, a food agent that pulls nearby
restaurants and cafes, a consolidator that builds the final plan and calls
a real tool to compute the budget total instead of stating one itself, and
a presenter that writes it up. Itinerary and food research now run
concurrently rather than one waiting on the other, a scheduling decision
confirmed safe against CrewAI's own source rather than assumed.
`tripcrew/app.py` is a working Streamlit chat, not a skeleton, it runs a
cheap intake-only check first and only kicks off the full crew once it has
enough to work with.

Weather, attractions, and restaurants call real APIs (OpenWeatherMap,
Geoapify). Restaurants reuse the same Geoapify integration attractions
does, but without a notability filter, a rating or popularity signal that
works for landmarks doesn't exist for restaurants. Both tools widen their
search radius once and try again before giving up, and the plan flags a
destination's results in the sidebar as a research gap if they came back
empty or too thin even after that, instead of presenting a short list as
if it were the whole picture. Attractions and restaurants also get a day
assignment, so a "3-day trip" is something the itinerary actually
structures around, not just a number on `TripPlan.days`. Flights and
hotels are mocked on purpose, not by oversight, the APIs with real live
pricing gate access behind a business-partner approval process that
doesn't clear on a reasonable timeline. See `docs/architecture.rst` for
the full reasoning and what the realistic path forward looks like.

Once a trip is fully planned, the sidebar offers it as a downloadable PDF
(`tripcrew/pdf_export.py`), built from the same consolidated `TripPlan`
the budget came from, not a re-formatted copy of the chat text. A
collapsed "How the agent got here" section shows each stage's own
reasoning, pulled from the real conversation transcript rather than the
structured output restated as JSON, and labeled unverified on purpose,
shown for transparency, never trusted as fact the way the plan's own
fields are.

The chat also switches modes once a trip's done: the next message stops
feeding the planning loop and becomes a follow-up question instead
(`tripcrew/followup.py`), answered by looking up real fields on that same
`TripPlan`, not by an LLM generating an answer from scratch. "Start over"
in the sidebar is the explicit way back to planning a different trip.

Testing: `tripcrew/evals/` and `tests/evals/` are a deepeval suite (chosen
over promptfoo, see `evaluation/README.md` for why) that checks whether
the presentation task's write-up actually says what's in the real plan,
using a judge model that reuses the crew's own LLM instead of requiring a
second API key. It's opt-in (`pytest -m eval`) since it calls a real model
over the network, everything else mocks its network calls and runs under
a plain `pytest`.

## What's not built

- A real flights/hotels API. Mocked data is a deliberate scope decision,
  not an oversight, see "Current state" above for why. Amadeus's sandbox
  is the realistic next step if this gets picked up, though its free tier
  is test data, not live pricing.
- A broader eval suite. Two cases today (a faithful write-up, one that
  fabricates an attraction), more fabrication shapes and other failure
  modes are real future work.
- CI. Nothing here runs `pytest` automatically yet, every check is manual.
- promptfoo. Only the deepeval half of the original two-tool eval plan got
  built, see `evaluation/README.md`.

One known limitation worth naming plainly: the presentation task's
write-up is generated before the plan's final correction pass runs
(`agent.py`'s `assemble_trip_plan()`), so its day-by-day framing and
research-gap mentions can occasionally disagree with what the sidebar and
PDF show, which reflect the corrected data. Treat the PDF's tables and the
sidebar as the source of truth, the write-up as presentation.

## Setup

The actual project lives under `tripcrew/` in this repo, most commands
below run from there. `.env` lives at this repo's root, one level up from
`tripcrew/`, since that's where python-dotenv's own upward search finds it
regardless of which directory a command is actually run from.

```bash
cp .env.example .env  # from here, the repo root -- then fill in real keys

cd tripcrew
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run tripcrew/app.py
```

See `docs/getting-started.rst` for the full walkthrough, including known
gotchas.

## Docs

Full documentation lives under `docs/` (Sphinx, set up for Read the Docs).
`docs/architecture.rst` covers the actual design and the real bugs each
decision fixes, described in prose on purpose rather than diagrams, see
that page's own opening for why.
