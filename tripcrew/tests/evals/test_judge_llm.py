"""Tests the parts of TripCrewJudgeLLM that never make a network call --
load_model() and get_model_name(). generate()/a_generate() are the two
methods that actually call the judge model, covered by the eval-marked
tests instead (test_writeup_groundedness.py), which exercise them
indirectly through a real deepeval metric.
"""

from crewai.llms.base_llm import BaseLLM

from tripcrew.evals.judge_llm import TripCrewJudgeLLM


def test_load_model_returns_the_projects_own_configured_llm():
    # Constructing TripCrewJudgeLLM() calls load_model() itself (see
    # DeepEvalBaseLLM.__init__), so this also confirms the constructor
    # doesn't make a network call on its own -- only generate()/
    # a_generate() should ever do that.
    #
    # Checked against BaseLLM, not crewai.LLM itself: crewai.LLM(...) is a
    # factory (confirmed directly -- build_llm()'s actual return type is
    # crewai.llms.providers.openai.completion.OpenAICompletion, not
    # crewai.llm.LLM), it dispatches to a concrete provider-specific
    # subclass based on the configured model string. BaseLLM is the real
    # common ancestor, and the interface (.call()/.acall()) this module's
    # generate()/a_generate() actually depend on.
    judge = TripCrewJudgeLLM()
    assert isinstance(judge.model, BaseLLM)
    assert hasattr(judge.model, "call") and hasattr(judge.model, "acall")


def test_get_model_name_does_not_make_a_network_call_and_returns_a_string():
    judge = TripCrewJudgeLLM()
    name = judge.get_model_name()
    assert isinstance(name, str)
    assert name
