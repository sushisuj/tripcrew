# Evaluation

Not built yet. This folder is a placeholder for two separate testing layers,
kept separate on purpose rather than picking one tool and using it for both.

promptfoo tests the agent's behavior: does it call tools in a sensible
order, does it actually ask for clarification when origin city or dates are
missing, does the plan structure stay stable across reruns on the same
input. This is the direct follow-up to a real problem hit on the
code-review-crew project, where the same file and same prompts gave
different findings between runs. That's not something you catch by
eyeballing output once.

deepeval tests answer quality once the PDF-to-chatbot handoff exists:
faithfulness of an answer to the generated itinerary, basically a more
rigorous version of the groundedness guardrail already built for
Constellate.
