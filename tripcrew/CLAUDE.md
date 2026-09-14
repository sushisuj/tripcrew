# Project instructions for Claude

## Who this is for

This file is read automatically by any Claude session working in this repo.
It exists so conventions don't have to be re-explained every time. Treat it
the same way the code-review-crew project's HANDOFF.md treats "don't
re-debug these."

## Writing style (README, docs, comments, PR descriptions, anything read as prose)

Sujan's voice, not generic AI-assistant prose. Specifics:

- No em dashes. Ever. Use commas, parentheses, or a full stop instead.
- Contractions are normal: "it's," "don't," "won't."
- Direct. State the point, then support it. Don't build up to it.
- Vary sentence length. Don't write uniform paragraphs of same-length sentences.
- Never use the "**Bold term**: explanation" list pattern. It's the most
  recognizable AI-writing tell there is.
- No filler openers ("It's important to note that...", "In today's fast-paced
  world..."), no filler closers (a summary paragraph restating what was just
  said), no signposting ("Let's explore...", "Now let's turn to...").
- Banned words: delve, dive into, navigate (figurative), underscore, bolster,
  foster, harness, leverage, unpack, pivotal, groundbreaking, cutting-edge,
  transformative, game-changing, innovative, robust, comprehensive, seamless,
  intricate, nuanced (as empty praise), vibrant, multifaceted, holistic,
  testament, landscape (figurative), realm.
- Banned structures: "It's not just X, it's Y." "Not only X, but Y." "This
  isn't about X, it's about Y." These sound like insight without containing any.
- Prose over bullet lists where prose actually reads fine. Lists are for
  genuinely enumerable things, not a default formatting style.
- Don't oversell status. If something's a skeleton, say it's a skeleton. If
  something's mocked, say it's mocked and say why. Honesty about what's not
  built yet is worth more than a confident-sounding README that overstates
  what's working.

## Repository layout: two `docs/` folders existed, only one is real

`docs/` at the repo root (sibling to this `tripcrew/` directory, i.e.
`Travel Planner/docs/`) is the actual Sphinx project. `conf.py`,
`index.rst`, `_static/`, `requirements.txt`, and the repo-root
`.readthedocs.yaml` (`sphinx: configuration: docs/conf.py`) only exist
there, and `index.rst`'s toctree is what actually pulls in
`getting-started` and `architecture`. A second `tripcrew/docs/` folder
existed alongside it with no Sphinx scaffolding of its own, not referenced
by any toctree, invisible to a Read the Docs build even if one were live.
It ended up with newer content than the real one purely by accident: work
done from inside a copy of this `tripcrew/` folder (this file included)
naturally treats paths as relative to that folder, so doc edits landed in
the orphan instead of the real site, and the real `docs/architecture.rst`
and `docs/getting-started.rst` went stale while the orphan kept getting
updated. Migrated the current content into the real `docs/` and removed
`tripcrew/docs/` entirely. If `docs/architecture.rst` or
`docs/getting-started.rst` ever look stale again, or a change is about to
write to a `docs/` path assuming this file's own directory is the project
root, check that assumption against the actual repo structure first,
that's exactly the mistake that created this.

## Project conventions

- Tool outputs are pydantic models (see `tripcrew/schemas.py`), not free
  text. This is what makes "evaluate the results" in the agent loop an
  actual step instead of a formality.
- Every model with a `source` field (`Flight`, `Hotel`) must be honest about
  where the data came from. `"mocked"` is a valid, expected value right
  now. It is not something to hide or work around.
- Don't let an LLM state a derived number (a total, a sum) and trust it.
  Compute it from the parts in code, the way `Budget.recompute()` does. This
  is a direct lesson from a real hallucination caught in the Constellate
  project: word-overlap or vocabulary-based checks catch missing terms, not
  wrong claims. The fix that actually works is not trusting the model for
  anything checkable by other means.
- A missing price is not a free item. `Budget.unpriced_categories` exists
  because `estimate_budget()` used to do `price or 0`, which silently turned
  "we don't know the cost" into "$0" (attractions hit this every time,
  Geoapify never returns cost data). If a category's cost is genuinely
  unknown, it goes in `unpriced_categories`, not folded into the total as
  zero, and the presentation task has to say so rather than show a total
  that looks complete.
- A category match is not notability. `get_attractions()`'s Places request
  used to filter on category alone, which is how a Lisbon trip came back
  with a minor spot in Trafaria, a separate town across the river, since
  Geoapify's circle search doesn't respect municipality boundaries. It now
  requests with Geoapify's `wiki_and_media` condition first (a real
  Wikipedia/Wikidata link, not just a category tag) and only falls back to
  the unfiltered search if that comes back empty, which happens for
  smaller destinations with thin Wikipedia coverage. Don't drop the
  notable-first request to "simplify" this, that's the actual fix.
- `estimate_budget()` and the weather date-matching logic
  (`_closest_forecast_entry()`) both have real test coverage now
  (`tests/test_budget.py`, `tests/test_weather.py`), mocking `requests.get`
  the same way `test_attractions.py` does. One behavior the budget tests
  document rather than fix: `unpriced_categories` only flags a category
  when *none* of its items have a price, so a mix of priced and unpriced
  attractions reports a real but incomplete total with no flag. Tighten
  that on purpose if it ever needs it, don't "fix" it as a side effect of
  touching something else.
- An approximate forecast is not a real one. `get_weather()` still returns
  the closest available entry for a date beyond OpenWeatherMap's 5-day free
  tier window, same as before, but `WeatherReport.is_approximate` now says
  when that happened. The itinerary, presentation, follow-up (`followup.py`),
  and PDF (`pdf_export.py`) code paths all check it and say "approximate"
  rather than presenting a nearby day's forecast as if it were the real one
  for that date. This isn't the seasonal-average fallback `weather.py` still
  mentions as the fuller fix, it's the honest version of the current
  approximation, not a replacement for it.
- `estimate_budget` is a real `@tool` now, and `consolidation_agent` has it
  as its one tool. This closed the gap where the LLM used to write
  `Budget.total_usd` itself as part of its own structured output, the exact
  thing the bullet above warns against. Don't strip that tool back off or
  let the consolidation task go back to computing a total from memory.
- Flights and hotels are mocked on purpose, not by oversight. See
  `docs/architecture.rst` for why (Skyscanner/Kiwi/Booking.com require
  business-partner approval with no workable timeline; Amadeus's free tier
  is sandbox data, not live pricing). Don't "fix" this by silently wiring in
  a real API without updating that doc and the `source` field values.
- Keep `.env` out of git. `.env.example` documents the shape without real
  keys. This has already gone wrong once in a different project on this
  account. Don't repeat it here.
- `tripcrew/app.py` has to fix its own `sys.path` before its `from
  tripcrew.xxx import ...` lines, don't remove that block thinking it's
  dead code. Confirmed by reading Streamlit's own `bootstrap.py`:
  `streamlit run tripcrew/app.py` only ever adds `app.py`'s own directory
  to `sys.path` (`_fix_sys_path()` does `os.path.dirname()` on the
  script's already-absolute path), never the project root one level up
  that `tripcrew` actually needs to resolve as a package. Without the
  shim, the documented run command fails with `ModuleNotFoundError: No
  module named 'tripcrew'` regardless of which directory it's launched
  from, `python -m streamlit run ...` happens to dodge it since `python
  -m` adds the current directory on its own, but that's incidental
  interpreter behavior, not something worth depending on.
- New tools should follow the shape already in `tripcrew/tools/`: a single
  `@tool`-decorated function, a pydantic return type from `schemas.py`, and
  a docstring that says what's real versus what's a placeholder.
- `tripcrew/pdf_export.py` is deliberately not under `tripcrew/tools/`: no
  agent calls it, app.py calls `build_trip_pdf()` directly once a trip is
  fully planned. Every number in it comes straight from `TripPlan.budget`,
  it never recomputes a total itself, same groundedness rule as the rest of
  this project. One easy-to-reintroduce bug if this gets touched: reportlab
  `Table` cells render plain strings literally (no XML parsing), but
  `Paragraph` objects parse `<`, `>`, `&` as markup, so `escape()` belongs
  on Paragraph text only, escaping a Table cell produces a literal
  `-&gt;` on the page. Confirmed by rendering a sample and reading it back,
  not just eyeballing the build succeeding.
- `tripcrew/followup.py` is the same "not an agent tool" case as
  `pdf_export.py`, plus one more rule specific to it: the LLM call in there
  (`build_intent_task`, `output_pydantic=TripQuestionIntent`) is only ever
  allowed to pick which field of `TripPlan` a question is about. It must
  never gain a code path that lets it draft the actual answer text --
  that's the one thing that would turn this from "graph traversal" back
  into the RAG pipeline the design explicitly avoids. `format_answer()`
  (plain Python) is the only thing allowed to produce the text a user sees.
- A category match is not curation, restaurant edition. `get_restaurants()`
  reuses the same Geoapify Places API and API key as `get_attractions()`,
  filtered to `catering.restaurant`, `catering.cafe`, and
  `catering.fast_food`, but it does not apply a notability condition the
  way attractions does. Checked directly against Geoapify's docs before
  building this: a place's properties carry name, address, categories,
  distance, and place_id, nothing Geoapify itself computes as a rating,
  popularity, or price-level signal, and `wiki_and_media` would come back
  near-empty for exactly the restaurants worth listing, a genuinely good
  neighborhood spot almost never has a Wikipedia page the way a landmark
  does. So `get_restaurants()` is a plain nearby-places search, and every
  place that presents it (the food task, the presentation task,
  `followup.py`, `pdf_export.py`) says so rather than implying curation
  that isn't there. If real curation ever matters, that's a new evaluation
  against something like Foursquare's ratings-bearing tier, not a filter
  to bolt onto this tool.
- `estimate_budget()` takes `restaurants` as a required argument alongside
  flights, hotel, and attractions, and `Budget` has a `restaurants_usd`
  field. Same unpriced-category handling as attractions: Geoapify doesn't
  return cost data for catering places either, so a real run always flags
  `"restaurants"` in `unpriced_categories` right now, not a bug, the
  honest state of the data.
- The consolidation task can't be trusted to restate attractions, weather,
  or restaurants either, same failure class as the `Budget.total_usd` bullet
  above, just applied to lists of text instead of a number. A real London
  run proved it: the weather table came back with "Light rain, ~22C
  (approximate) (approximate)", a corruption `get_weather()` itself never
  produces, introduced only by `build_consolidation_task`'s LLM re-authoring
  `TripPlan.weather` from context instead of copying it. Fixed by giving
  `build_itinerary_task`/`build_itinerary_task_from_plan` and
  `build_food_task`/`build_food_task_from_plan` their own `output_pydantic`
  types (`ItineraryResearch`, `FoodResearch` in `schemas.py`), and adding
  `agent.py`'s `assemble_trip_plan()`, which finds the consolidation task's
  `TripPlan` and overwrites its `attractions`/`weather`/`restaurants` with
  those two tasks' real structured output before anything downstream sees
  it. `app.py` calls `assemble_trip_plan()`, it doesn't read the
  consolidation task's `TripPlan` directly any more. If a new research
  field ever gets added to the itinerary or food task, it needs the same
  treatment (a real `output_pydantic` type, plus a line in
  `assemble_trip_plan()`), not just a mention in the consolidation task's
  own output, or it inherits this same restating risk.
- `app.py`'s `STAGE_LABELS` list has to have exactly as many entries as
  `build_crew(intake_plan=...)` has tasks, since `task_callback` fires once
  per completed task and counts against that list by index. Adding a role
  to the crew (food research did this) without adding its label here means
  the last real stage silently stops showing a checkmark, `mark_stage_done`
  swallows the resulting index-out-of-range case on purpose, so this fails
  quiet, not loud, if forgotten.

## Architecture note: multi-agent, not single-agent

The agent layer was originally a single agent with four tools. That's
been superseded. The actual design is a five-role crew under
`Process.sequential` (intake/coordinator, itinerary research, food
research, consolidation, presentation), described in full in
`docs/architecture.rst`. All five roles are wired into `build_crew()` now,
including food research (`build_food_agent()`, `build_food_task()`/
`build_food_task_from_plan()`). Don't rebuild the single-agent version, and
don't assume `tripcrew/agent.py` still matches this file's own earlier
description of it, check the current code and `docs/architecture.rst`
directly.

The clarification loop is built, as two separate crews, not one crew that
pauses mid-run: `build_intake_crew()` checks `TripPlan.open_questions`,
`app.py` shows them and waits for the next message if non-empty, then
calls `build_crew(intake_plan=...)` once satisfied, passing that draft
straight in so the full crew doesn't rerun intake from scratch. Full
reasoning in `docs/architecture.rst`'s "Clarification loop" section.

## Not built yet (don't assume these exist)

- promptfoo and deepeval test suites (see `evaluation/README.md` for the
  intended split between them).
