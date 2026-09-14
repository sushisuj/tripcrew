"""A deepeval-compatible judge model that reuses this project's own LLM.

deepeval's built-in metrics (FaithfulnessMetric, HallucinationMetric, GEval,
and the rest) each need an LLM to act as the judge that scores a test case --
by default that's OpenAI's own API, gated on a real OPENAI_API_KEY pointed at
api.openai.com. This project already has an OPENAI_API_KEY in .env, but it's
deliberately pointed at NVIDIA NIM instead (OPENAI_API_BASE, see
agent.build_llm()'s own docstring for why: Groq's free tier kept
rate-limiting mid-run). Using deepeval's default judge here would silently
require a second, unrelated OpenAI account and key just to run evals, on top
of the one this project already asks for. TripCrewJudgeLLM avoids that by
wrapping the exact same LLM object the crew itself runs on.

deepeval's own interface for this is DeepEvalBaseLLM (confirmed by reading
its source, deepeval/models/base_model.py): a subclass implements
load_model(), generate(), a_generate(), and get_model_name(). Only
generate()/a_generate() ever make a real network call -- load_model() and
get_model_name() are pure and safe to call from a normal (non-eval-marked)
test, see tests/evals/test_judge_llm.py.
"""

from typing import TypeVar

from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

from tripcrew.agent import build_llm

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


class TripCrewJudgeLLM(DeepEvalBaseLLM):
    """Judge model for deepeval metrics, backed by agent.build_llm() (the
    same NVIDIA NIM Nemotron model the crew's own agents run on, see that
    function's own docstring). Pass an instance of this to any deepeval
    metric's `model=` argument instead of leaving it unset.
    """

    def load_model(self) -> "object":
        """Returns the real object agent.build_llm() constructs, not
        deepeval's own base client. crewai.LLM(...) is a factory, not a
        concrete class -- confirmed directly: build_llm()'s actual return
        type is crewai.llms.providers.openai.completion.OpenAICompletion,
        a crewai.llms.base_llm.BaseLLM subclass, not crewai.llm.LLM itself
        -- which provider-specific class it dispatches to depends on the
        configured model string, but .call()/.acall() (used below) are
        BaseLLM's own interface either way, not specific to this one
        provider. Same object every other part of this project already
        depends on, no reason to route through a second HTTP client
        library just for evals.
        """
        return build_llm()

    def generate(self, prompt: str, schema: type[_SchemaT] | None = None) -> str | _SchemaT:
        """Some deepeval metrics ask the judge for a structured response
        (a schema kwarg) so they can parse a score/reason pair reliably
        instead of regex-scraping free text -- confirmed by reading
        DeepEvalBaseLLM.generate_with_schema(), which calls generate(...,
        schema=schema) and only falls back to plain text if that raises
        TypeError. self.model's own .call() (BaseLLM's interface, see
        load_model()'s docstring) already supports exactly this via its
        own response_model argument, confirmed directly against its
        signature, so this passes schema straight through instead of
        hand-rolling JSON parsing here.
        """
        if schema is not None:
            return self.model.call(prompt, response_model=schema)
        return self.model.call(prompt)

    async def a_generate(self, prompt: str, schema: type[_SchemaT] | None = None) -> str | _SchemaT:
        """self.model has a real async call (.acall(), confirmed directly
        against its signature, same response_model support as .call()) --
        used here rather than falling back to the sync generate(), so a
        metric that issues several judge calls concurrently actually gets
        real concurrency instead of blocking on each one in turn.
        """
        if schema is not None:
            return await self.model.acall(prompt, response_model=schema)
        return await self.model.acall(prompt)

    def get_model_name(self) -> str:
        """Not the underlying model string (self.model.model, e.g.
        "openai/nvidia/nemotron-3-ultra-550b-a55b") -- deepeval uses
        get_model_name() purely for display (metric result printouts,
        --verbose output), and this project's own model ID is already
        documented in build_llm()'s docstring for anyone who needs it.
        Named after what this actually is instead: the crew's own judge,
        not a separate eval-specific model choice.
        """
        return "tripcrew's own crew LLM (see agent.build_llm())"
