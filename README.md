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
