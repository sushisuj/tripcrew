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

Early. The package structure, schemas, and tool interfaces exist. Weather
and attractions call real APIs (OpenWeatherMap, OpenTripMap). Flights and
hotels are mocked on purpose, not by oversight, because the APIs with real
live pricing gate access behind a business-partner approval process that
doesn't clear on a reasonable timeline. See `docs/architecture.rst` for the
full reasoning and what the realistic path forward looks like.

The agent itself is wired up (`tripcrew/agent.py`) but the multi-turn
clarification loop, the part that actually lets it pause and ask "what
dates?" instead of guessing, isn't built yet. `tripcrew/app.py` is a
Streamlit skeleton, not a working chat flow.

## Where this is headed

The plan, in rough order:

1. The clarification loop and the full plan-tools-evaluate-respond cycle,
   actually working end to end on mocked flight/hotel data.
2. Basic error handling for tool and API failures, so a missing weather
   result degrades to "weather unavailable" instead of crashing the run.
3. Exporting the finished itinerary to PDF.
4. A follow-up step where that PDF becomes something you can ask questions
   about, reusing document Q&A ideas from a separate project rather than
   the RAG chatbot itself. A single generated itinerary is small enough
   that this probably means putting it directly in context, not standing
   up a vector store for a two-page document. Worth deciding deliberately
   rather than defaulting to whichever approach is already lying around.
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
