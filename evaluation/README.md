# Evaluation

This folder was a placeholder for two separate testing layers, kept
separate on purpose rather than picking one tool and using it for both.
Only one of the two actually got built, and not here: see
`tripcrew/evals/` and `tests/evals/` for the real deepeval suite
(`docs/architecture.rst`'s "Live-judge evaluation suite" section has the
full reasoning), and `CLAUDE.md`'s matching bullet for the conventions
around it. This file is kept around for the promptfoo half, which is
still real future work, not to describe the deepeval half, that's out of
date the moment the code below is read instead of this file.

promptfoo would test the agent's behavior: does it call tools in a
sensible order, does it actually ask for clarification when origin city
or dates are missing, does the plan structure stay stable across reruns
on the same input. This is the direct follow-up to a real problem hit on
the code-review-crew project, where the same file and same prompts gave
different findings between runs. That's not something you catch by
eyeballing output once. Not built. Deepeval was picked first because it
fit this project's existing pytest-based testing style, one runner and
config format instead of two; promptfoo would be a genuinely separate
addition, not a natural next step off the deepeval work.

deepeval tests answer quality: does the presentation task's write-up
actually say what's in the real `TripPlan`, or does it drift the way the
consolidation task's own restating once did (the corrupted weather
summary bug, see `agent.py`'s `assemble_trip_plan()` docstring). Built,
in `tripcrew/evals/` and `tests/evals/`, not in this folder. Two cases
today (a faithful write-up, one that fabricates an attraction), not an
exhaustive suite, more fabrication shapes, a dropped `research_gap`, a
misstated price, are real future work.

Using both for the same thing would be redundant, they're deliberately
scoped to different layers of the system, agent behavior versus output
faithfulness. That reasoning hasn't changed even though only one side got
built.
