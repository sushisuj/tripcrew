Getting started
===============

Environment setup
------------------

.. code-block:: bash

   python3.10 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

Then create a ``.env`` file (never committed -- see ``.env.example`` for the
shape) with your own API keys:

.. code-block:: text

   OPENAI_API_KEY=<nvidia-nim-key>
   OPENAI_API_BASE=https://integrate.api.nvidia.com/v1
   OPENWEATHER_API_KEY=<openweathermap-key>
   GEOAPIFY_API_KEY=<geoapify-key>

Running the app
----------------

.. code-block:: bash

   streamlit run tripcrew/app.py

Running tests
--------------

.. code-block:: bash

   pytest

Known gotchas
--------------

The LLM is NVIDIA NIM again, on Nemotron 3 Ultra
(``nvidia/nemotron-3-ultra-550b-a55b``), not the Groq setup this project
briefly moved to. Switched back because Groq's free tier (8000 tokens per
minute on ``openai/gpt-oss-20b``) kept rate-limiting mid-run even after
cutting a redundant LLM call from the pipeline, see ``agent.py``'s
``build_crew()`` docstring. The ``openai/`` prefix in the model string is
required, same as the original NVIDIA setup: it forces LiteLLM's generic
OpenAI-compatible path instead of matching ``nvidia/...`` against some
other registered provider and failing auth.

CrewAI (as of 1.15.x) has a bug where it tags every message with a
``cache_breakpoint`` flag meant only for Anthropic's API, regardless of
which provider is actually configured
(github.com/crewAIInc/crewAI/issues/5886). Confirmed on Groq that this
causes a hard failure (some endpoints validate message schemas strictly
and reject the unrecognized field); NVIDIA NIM's tolerance for it hasn't
been separately confirmed, so the workaround in ``agent.py`` (patching
``mark_cache_breakpoint`` to a no-op) is left in place regardless of
provider. Harmless either way, only remove it if this project ever
switches to an actual Anthropic model.
