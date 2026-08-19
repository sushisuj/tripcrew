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
  OpenTripMap never returns cost data). If a category's cost is genuinely
  unknown, it goes in `unpriced_categories`, not folded into the total as
  zero, and the presentation task has to say so rather than show a total
  that looks complete.
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
- New tools should follow the shape already in `tripcrew/tools/`: a single
  `@tool`-decorated function, a pydantic return type from `schemas.py`, and
  a docstring that says what's real versus what's a placeholder.

## Architecture note: multi-agent, not single-agent

The agent layer was originally a single agent with four tools. That's
been superseded. The actual design is a five-role crew under
`Process.sequential` (intake/coordinator, itinerary research, food
research, consolidation, presentation), described in full in
`docs/architecture.rst`. Don't rebuild the single-agent version, and don't
assume `tripcrew/agent.py` still matches this file's own earlier
description of it, check the current code and `docs/architecture.rst`
directly.

The clarification loop is built, as two separate crews, not one crew that
pauses mid-run: `build_intake_crew()` checks `TripPlan.open_questions`,
`app.py` shows them and waits for the next message if non-empty, then
calls `build_crew()` once satisfied. Full reasoning in
`docs/architecture.rst`'s "Clarification loop" section, including the
known inefficiency of intake running twice.

## Not built yet (don't assume these exist)

- The five-agent crew itself. Currently four roles are working, food
  research is deferred until its tool exists.
- The food/restaurant search tool (planned: OpenTripMap, same pattern as
  `attractions.py`, different `kinds` filter).
- PDF export of the finished plan.
- The follow-up chatbot, now planned as a knowledge graph over the
  generated `TripPlan` (graph traversal, not an LLM call, not a RAG
  pipeline), explicitly a separate later phase. See
  `docs/architecture.rst` for why this is a better fit than reusing
  Constellate's RAG stack.
- promptfoo and deepeval test suites (see `evaluation/README.md` for the
  intended split between them).
