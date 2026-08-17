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

## Not built yet (don't assume these exist)

- The multi-turn clarification loop (the agent asking for missing info and
  waiting for an answer). `tripcrew/app.py` is a UI skeleton only.
- Error handling for tool/API failures beyond raising an exception.
- PDF export of the finished plan.
- The optional follow-up chatbot that would answer questions about a
  generated plan (would reuse ideas from the Constellate project, but
  should not naively import its full RAG pipeline. A single generated
  itinerary is small enough to put directly in context, no vector search
  needed, unless there's a specific reason to demonstrate the RAG stack
  again deliberately).
- promptfoo and deepeval test suites (see `evaluation/README.md` for the
  intended split between them).
